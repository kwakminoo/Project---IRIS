"""Playwright 웹 검색·페이지 리서치 (읽기 전용, 기본 headless)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Sequence
from urllib.parse import quote_plus, urlparse

# 로그인·결제·개인정보 입력 페이지 — 본문만 읽고 클릭·입력·제출 금지
_SENSITIVE_URL = re.compile(
    r"(login|signin|sign-in|signup|sign-up|register|oauth|auth/|account/|"
    r"checkout|payment|pay\.|billing|cart|주문|결제|로그인|회원가입|비밀번호)",
    re.IGNORECASE,
)
_SENSITIVE_TEXT = re.compile(
    r"(password|credit\s*card|cvv|cvc|주민\s*번호|계좌\s*번호|카드\s*번호|"
    r"personal\s*information|개인\s*정보\s*입력)",
    re.IGNORECASE,
)
_DATE_META_KEYS = (
    "article:published_time",
    "og:updated_time",
    "datePublished",
    "pubdate",
    "publishdate",
    "date",
)
_DATE_IN_TEXT = re.compile(
    r"(\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}일?|\d{4}-\d{2}-\d{2})"
)
_SKIP_DOMAINS = ("google.com", "youtube.com/redirect", "accounts.google")


@dataclass
class SearchHit:
    """검색·페이지 리서치 한 출처."""

    title: str
    url: str
    snippet: str
    date_candidate: str = ""
    read_only_restricted: bool = False  # 민감 페이지로 본문 추출 제한
    source_label: str = ""  # SERP | page


def google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def is_sensitive_url(url: str) -> bool:
    """URL만으로 민감 페이지 여부 추정."""
    if not url:
        return False
    low = url.lower()
    if _SENSITIVE_URL.search(low):
        return True
    for skip in _SKIP_DOMAINS:
        if skip in low:
            return False
    return False


def extract_date_candidate(page_text: str, meta: dict[str, str] | None = None) -> str:
    """메타·본문에서 날짜 후보 추출."""
    if meta:
        for key in _DATE_META_KEYS:
            val = meta.get(key) or meta.get(key.lower())
            if val and isinstance(val, str):
                v = val.strip()[:32]
                if v:
                    return v
    if page_text:
        m = _DATE_IN_TEXT.search(page_text[:4000])
        if m:
            return m.group(1).strip()
    return ""


def build_body_snippet(paragraphs: Sequence[str], max_chars: int = 480) -> str:
    """본문 단락에서 요약 스니펫 생성."""
    parts: list[str] = []
    total = 0
    for p in paragraphs:
        t = re.sub(r"\s+", " ", p).strip()
        if len(t) < 24:
            continue
        if total + len(t) > max_chars:
            remain = max_chars - total
            if remain > 40:
                parts.append(t[:remain] + "…")
            break
        parts.append(t)
        total += len(t)
    return " ".join(parts)


def _playwright_headless() -> bool:
    """기본 True — 검색 시 브라우저 창을 띄우지 않음 (IRIS_PLAYWRIGHT_HEADLESS=0 이면 표시)."""
    raw = os.getenv("IRIS_PLAYWRIGHT_HEADLESS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _playwright_unavailable_hit(error: Exception) -> SearchHit:
    return SearchHit(
        title="Playwright 미설치",
        url="",
        snippet=f"pip install playwright 후 python -m playwright install chromium: {error}",
        source_label="error",
    )


def fetch_search_hits(query: str, max_results: int = 8) -> List[SearchHit]:
    """SERP에서 링크 수집 (페이지 본문은 enrich_research_hits에서)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return [_playwright_unavailable_hit(e)]

    hits: List[SearchHit] = []
    seen_domains: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=_playwright_headless())
        page = browser.new_page()
        try:
            page.goto(google_search_url(query), timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            for a in page.query_selector_all("a"):
                try:
                    href = a.get_attribute("href") or ""
                    text = (a.inner_text() or "").strip().replace("\n", " ")
                    if not href.startswith("http"):
                        continue
                    if any(s in href for s in _SKIP_DOMAINS):
                        continue
                    dom = _domain(href)
                    if dom in seen_domains:
                        continue
                    if len(text) < 2:
                        continue
                    seen_domains.add(dom)
                    hits.append(
                        SearchHit(
                            title=text[:120],
                            url=href,
                            snippet="",
                            source_label="serp",
                        )
                    )
                    if len(hits) >= max_results:
                        break
                except Exception:
                    continue
        finally:
            browser.close()

    if not hits:
        return [
            SearchHit(
                "결과 없음",
                google_search_url(query),
                "검색 페이지를 확인해 주세요.",
                source_label="serp",
            )
        ]
    return hits


def _read_page_research(page, url: str, title_hint: str) -> SearchHit:
    """단일 페이지 읽기 전용 추출. 폼 입력·클릭·제출 없음."""
    restricted = is_sensitive_url(url)
    title = title_hint[:120] if title_hint else url
    snippet = ""
    date_candidate = ""
    meta: dict[str, str] = {}

    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
    except Exception as exc:
        return SearchHit(
            title=title,
            url=url,
            snippet=f"페이지 로드 실패: {exc}",
            source_label="page",
            read_only_restricted=restricted,
        )

    # 비밀번호 필드가 있으면 민감 페이지로 간주
    try:
        if page.locator('input[type="password"]').count() > 0:
            restricted = True
    except Exception:
        pass

    try:
        doc_title = (page.title() or "").strip()
        if doc_title:
            title = doc_title[:200]
    except Exception:
        pass

    if restricted:
        return SearchHit(
            title=title,
            url=url,
            snippet="[민감 페이지] 로그인·결제·개인정보 입력 영역으로 본문 추출을 생략했습니다. (읽기 전용)",
            date_candidate="",
            read_only_restricted=True,
            source_label="page",
        )

    try:
        for el in page.query_selector_all("meta"):
            name = (el.get_attribute("name") or el.get_attribute("property") or "").lower()
            content = el.get_attribute("content") or ""
            if name and content:
                meta[name] = content.strip()
    except Exception:
        pass

    paragraphs: list[str] = []
    selectors = (
        "article p",
        "main p",
        '[role="main"] p',
        ".article-body p",
        ".post-content p",
        "p",
    )
    try:
        for sel in selectors:
            nodes = page.query_selector_all(sel)
            if len(nodes) >= 2:
                for node in nodes[:24]:
                    t = (node.inner_text() or "").strip()
                    if t:
                        paragraphs.append(t)
                break
    except Exception:
        pass

    body_sample = " ".join(paragraphs)[:6000]
    if _SENSITIVE_TEXT.search(body_sample):
        return SearchHit(
            title=title,
            url=url,
            snippet="[민감 페이지] 개인정보·결제 관련 문구가 감지되어 본문 추출을 생략했습니다.",
            read_only_restricted=True,
            source_label="page",
        )

    desc = meta.get("description") or meta.get("og:description") or ""
    snippet = build_body_snippet(paragraphs) if paragraphs else desc[:480]
    if not snippet and desc:
        snippet = desc[:480]

    date_candidate = extract_date_candidate(body_sample, meta)
    try:
        time_el = page.query_selector("time[datetime]")
        if time_el:
            dt = time_el.get_attribute("datetime")
            if dt:
                date_candidate = date_candidate or dt[:32]
    except Exception:
        pass

    return SearchHit(
        title=title,
        url=url,
        snippet=snippet or "(본문 요약 없음)",
        date_candidate=date_candidate,
        read_only_restricted=False,
        source_label="page",
    )


def enrich_research_hits(
    serp_hits: Sequence[SearchHit],
    *,
    max_pages: int = 5,
) -> List[SearchHit]:
    """SERP 상위 링크 중 max_pages개를 열어 제목·URL·날짜·본문 스니펫 추출."""
    if not serp_hits:
        return []
    if serp_hits[0].title == "Playwright 미설치":
        return list(serp_hits)

    candidates = [h for h in serp_hits if h.url.startswith("http") and h.title != "결과 없음"]
    to_visit = candidates[:max(3, min(max_pages, 5))]

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return list(serp_hits)

    enriched: List[SearchHit] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=_playwright_headless())
        page = browser.new_page()
        try:
            for hit in to_visit:
                if is_sensitive_url(hit.url):
                    enriched.append(
                        SearchHit(
                            title=hit.title,
                            url=hit.url,
                            snippet="[민감 페이지] URL 패턴상 본문 방문을 생략했습니다.",
                            read_only_restricted=True,
                            source_label="page",
                        )
                    )
                    continue
                enriched.append(_read_page_research(page, hit.url, hit.title))
        finally:
            browser.close()

    # 방문하지 않은 SERP 항목은 링크만 유지
    visited_urls = {h.url for h in enriched}
    for h in serp_hits:
        if h.url not in visited_urls:
            enriched.append(h)
    return enriched


def fetch_research_hits(query: str, *, max_serp: int = 8, max_pages: int = 5) -> List[SearchHit]:
    """검색 후 상위 페이지 리서치까지 한 번에 수행."""
    serp = fetch_search_hits(query, max_results=max_serp)
    return enrich_research_hits(serp, max_pages=max_pages)


def extract_query_from_text(text: str) -> str:
    """사용자 문장에서 검색어 추출 (간단)."""
    t = text.strip()
    for prefix in ("검색해줘", "검색 해줘", "웹 검색", "자료 찾아줘", "자료 찾아"):
        if t.startswith(prefix):
            t = t[len(prefix) :].strip(" :,.")
    t = re.sub(r"(요약해줘|보고서로\s*정리)", "", t).strip()
    return t or "Iris assistant"
