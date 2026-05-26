"""YouTube 검색 결과 DOM → watch URL 선택 (제목·링크만, HTML/스크린샷 저장 없음)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse, urlunparse


def _query_tokens(query: str) -> list[str]:
    raw = re.findall(r"[\w가-힣]{2,}", query.strip().lower())
    seen: set[str] = set()
    out: list[str] = []
    for t in raw:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _token_overlap_score(text: str, query_tokens: list[str]) -> float:
    if not query_tokens:
        return 1.0
    text_tokens = set(re.findall(r"[\w가-힣]+", text.lower()))
    if not text_tokens:
        return 0.0
    hits = sum(
        1
        for t in query_tokens
        if t in text_tokens or any(t in wt or wt in t for wt in text_tokens)
    )
    return hits / len(query_tokens)

_YOUTUBE_WATCH_RE = re.compile(
    r"https?://(?:www\.)?youtube\.com/watch\?[^#\s]*v=[\w-]+",
    re.I,
)
_BLOCKED_HREF = re.compile(r"/shorts/|googleads|doubleclick|/adview|/pagead", re.I)
_MAX_CANDIDATES = 8


@dataclass(frozen=True)
class YoutubeWatchCandidate:
    """DOM에서 수집한 검색 결과 1건."""

    title: str
    url: str


def extract_video_id(url: str) -> str:
    """로그용 videoId만 추출 (원문 URL 전체 저장 최소화)."""
    try:
        parsed = urlparse(url)
        if "youtu.be" in parsed.netloc:
            vid = parsed.path.strip("/").split("/")[0]
            return vid[:32] if vid else ""
        qs = parse_qs(parsed.query)
        vid = (qs.get("v") or [""])[0]
        return str(vid)[:32]
    except Exception:
        return ""


def normalize_watch_url(href: str) -> str | None:
    """watch?v= URL 정규화 — Shorts·광고·비표준 제외."""
    raw = (href or "").strip()
    if not raw or _BLOCKED_HREF.search(raw):
        return None
    if raw.startswith("/"):
        raw = f"https://www.youtube.com{raw}"
    if not raw.startswith("http"):
        return None
    if "/shorts/" in raw.lower():
        return None
    m = _YOUTUBE_WATCH_RE.search(raw)
    if not m:
        if "watch?v=" not in raw.lower():
            return None
        parsed = urlparse(raw)
        if "youtube.com" not in parsed.netloc:
            return None
        qs = parse_qs(parsed.query)
        vid = (qs.get("v") or [""])[0]
        if not vid or len(vid) < 6:
            return None
        return urlunparse(
            (
                "https",
                "www.youtube.com",
                "/watch",
                "",
                f"v={vid}",
                "",
            )
        )
    return m.group(0).split("&")[0] if "&" in m.group(0) else m.group(0)


def parse_youtube_search_results(raw: Any) -> list[YoutubeWatchCandidate]:
    """확장·ingest JSON → 후보 목록 (제목·URL만)."""
    if not isinstance(raw, list):
        return []
    out: list[YoutubeWatchCandidate] = []
    seen: set[str] = set()
    for item in raw[:_MAX_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = normalize_watch_url(str(item.get("url") or item.get("href") or ""))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        out.append(YoutubeWatchCandidate(title=title[:240], url=url))
        if len(out) >= _MAX_CANDIDATES:
            break
    return out


def filter_youtube_watch_results(
    candidates: list[YoutubeWatchCandidate],
) -> list[YoutubeWatchCandidate]:
    """Shorts·광고 URL 재검증."""
    kept: list[YoutubeWatchCandidate] = []
    for c in candidates:
        if _BLOCKED_HREF.search(c.url):
            continue
        if "/shorts/" in c.url.lower():
            continue
        kept.append(c)
    return kept[:_MAX_CANDIDATES]


def pick_watch_url_by_tokens(
    search_query: str,
    candidates: list[YoutubeWatchCandidate],
) -> YoutubeWatchCandidate | None:
    """검색어 토큰 겹침으로 watch URL 1개 선택."""
    if not candidates:
        return None
    tokens = _query_tokens(search_query)
    if not tokens:
        return candidates[0]
    best: YoutubeWatchCandidate | None = None
    best_score = -1.0
    for c in candidates:
        score = _token_overlap_score(c.title, tokens)
        if score > best_score:
            best_score = score
            best = c
    return best or candidates[0]


def pick_watch_url(
    search_query: str,
    candidates: list[YoutubeWatchCandidate],
    *,
    rank_pick_title: Callable[[list[str]], str | None] | None = None,
) -> YoutubeWatchCandidate | None:
    """토큰 겹침 우선, 선택적 Ranker(제목 목록) 폴백."""
    filtered = filter_youtube_watch_results(candidates)
    if not filtered:
        return None
    if rank_pick_title:
        titles = [c.title for c in filtered]
        pick_title = rank_pick_title(titles)
        if pick_title:
            for c in filtered:
                if c.title == pick_title or pick_title in c.title or c.title in pick_title:
                    return c
    return pick_watch_url_by_tokens(search_query, filtered)
