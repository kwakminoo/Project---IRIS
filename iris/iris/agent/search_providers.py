"""검색 API·Open-Meteo·TMDB — SearXNG/DDG HTML·Playwright Google SERP (유료 API 미사용)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Literal, Sequence
from urllib.parse import urlparse

import httpx

from iris.agent.web_agent import SearchHit
from iris.core.activity_sink import push_activity_line
from iris.core.command_router import CommandKind

_HTTP_TIMEOUT = 20.0
_DDG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Open-Meteo WMO weather_code → 한국어 (요약용)
_WMO_KO: dict[int, str] = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "짙은 안개",
    51: "이슬비",
    53: "이슬비",
    55: "강한 이슬비",
    61: "비",
    63: "비",
    65: "폭우",
    71: "눈",
    73: "눈",
    75: "폭설",
    80: "소나기",
    81: "소나기",
    82: "강한 소나기",
    95: "뇌우",
}


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _provider_error_hit(title: str, detail: str) -> SearchHit:
    return SearchHit(
        title=title,
        url="",
        snippet=f"[API 오류] {detail}",
        source_label="provider_error",
    )


def _default_lat_lon() -> tuple[float, float]:
    lat = float(os.getenv("OPEN_METEO_DEFAULT_LAT", "37.5665"))
    lon = float(os.getenv("OPEN_METEO_DEFAULT_LON", "126.9780"))
    return lat, lon


def _weather_place_hint(query: str) -> str:
    """검색 질의에서 지명 후보 추출."""
    t = query.strip()
    for token in (
        "오늘",
        "내일",
        "모레",
        "날씨",
        "어때",
        "어떄",
        "알려줘",
        "알려",
        "궁금",
        "말해줘",
        "은",
        "는",
        "이",
        "가",
    ):
        t = t.replace(token, " ")
    t = re.sub(r"\s+", " ", t).strip(" ?.,!")
    return t or "Seoul"


def fetch_open_meteo_hits(query: str) -> List[SearchHit]:
    """Open-Meteo — API 키 불필요."""
    place = _weather_place_hint(query)
    lat_d, lon_d = _default_lat_lon()
    lat, lon, label = lat_d, lon_d, "서울(기본)"
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            if place and place.lower() not in ("seoul", "서울"):
                geo = client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": place, "count": 1, "language": "ko"},
                )
                geo.raise_for_status()
                results = geo.json().get("results") or []
                if results:
                    r0 = results[0]
                    lat = float(r0["latitude"])
                    lon = float(r0["longitude"])
                    label = str(r0.get("name") or place)
            fc = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "timezone": "Asia/Seoul",
                },
            )
            fc.raise_for_status()
            data = fc.json()
    except Exception as exc:
        return [_provider_error_hit("Open-Meteo 조회 실패", str(exc))]

    cur = data.get("current") or {}
    temp = cur.get("temperature_2m")
    hum = cur.get("relative_humidity_2m")
    wcode = int(cur.get("weather_code") or 0)
    wind = cur.get("wind_speed_10m")
    desc = _WMO_KO.get(wcode, f"코드 {wcode}")
    parts: list[str] = [f"{label} 현재 날씨: {desc}"]
    if temp is not None:
        parts.append(f"기온 {temp}°C")
    if hum is not None:
        parts.append(f"습도 {hum}%")
    if wind is not None:
        parts.append(f"풍속 {wind} km/h")
    snippet = ", ".join(parts)
    url = (
        f"https://open-meteo.com/en/docs"
        f"#latitude={lat}&longitude={lon}"
    )
    return [
        SearchHit(
            title=f"{label} 날씨 (Open-Meteo)",
            url=url,
            snippet=snippet,
            date_candidate=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            source_label="open_meteo",
        )
    ]


def fetch_tmdb_hits(query: str, *, max_results: int = 5) -> List[SearchHit]:
    """TMDB — 인기/검색 영화."""
    key = os.getenv("TMDB_API_KEY", "").strip()
    if not key:
        return [
            _provider_error_hit(
                "TMDB API 키 없음",
                ".env에 TMDB_API_KEY를 설정하세요. https://www.themoviedb.org/settings/api",
            )
        ]

    q = query.strip()
    movie_keywords = ("영화", "무비", "개봉", "재밌", "추천", "뭐 있", "뭐있")
    use_popular = not q or any(k in q for k in movie_keywords) and len(q) < 24

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            if use_popular:
                resp = client.get(
                    "https://api.themoviedb.org/3/movie/popular",
                    params={"api_key": key, "language": "ko-KR", "page": 1},
                )
            else:
                search_q = re.sub(r"(요즘|재밌는|인기|영화|뭐\s*있어)", " ", q).strip() or q
                resp = client.get(
                    "https://api.themoviedb.org/3/search/movie",
                    params={
                        "api_key": key,
                        "language": "ko-KR",
                        "query": search_q,
                        "page": 1,
                    },
                )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        return [_provider_error_hit("TMDB 조회 실패", str(exc))]

    items = payload.get("results") or []
    hits: List[SearchHit] = []
    for item in items[:max_results]:
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        mid = item.get("id")
        overview = str(item.get("overview") or "").strip()
        date = str(item.get("release_date") or item.get("first_air_date") or "")[:10]
        url = f"https://www.themoviedb.org/movie/{mid}" if mid else "https://www.themoviedb.org/"
        snip = overview[:400] if overview else f"개봉일 후보: {date}" if date else title
        hits.append(
            SearchHit(
                title=title,
                url=url,
                snippet=snip,
                date_candidate=date,
                source_label="tmdb",
            )
        )
    if not hits:
        return [_provider_error_hit("TMDB 결과 없음", f"질의: {query}")]
    return hits


def _searxng_engines_param() -> str:
    """P2 — 단일 Google 엔진 의존 완화. SEARXNG_ENGINES로 다변화(쉼표 구분)."""
    raw = os.getenv("SEARXNG_ENGINES", "google,bing,duckduckgo,wikipedia").strip()
    engines = [e.strip() for e in raw.split(",") if e.strip()]
    return ",".join(engines) if engines else "google,bing,duckduckgo"


def fetch_searxng_hits(query: str, *, max_results: int = 6) -> List[SearchHit]:
    base = os.getenv("SEARXNG_BASE_URL", "").strip().rstrip("/")
    if not base:
        return []
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(
                f"{base}/search",
                params={
                    "q": query,
                    "format": "json",
                    "engines": _searxng_engines_param(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return [_provider_error_hit("SearXNG 실패", str(exc))]

    hits: List[SearchHit] = []
    for item in data.get("results") or []:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        if not url:
            continue
        hits.append(
            SearchHit(
                title=title[:200] or url[:80],
                url=url,
                snippet=(content or str(item.get("snippet") or ""))[:480],
                source_label="searxng",
            )
        )
    return hits[:max_results]


def fetch_duckduckgo_hits(query: str, *, max_results: int = 6) -> List[SearchHit]:
    """키/도커 없이 동작하는 기본 웹 검색(HTML 결과 파싱)."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": q},
                headers={"User-Agent": _DDG_UA},
            )
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        return [_provider_error_hit("DuckDuckGo 조회 실패", str(exc))]

    hits: List[SearchHit] = []
    # result title/url
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippets = re.findall(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(html)
    for idx, (href, raw_title) in enumerate(matches[:max_results]):
        title = re.sub(r"<[^>]+>", "", raw_title)
        title = re.sub(r"\s+", " ", title).strip()
        snippet_raw = snippets[idx] if idx < len(snippets) else ""
        snippet = re.sub(r"<[^>]+>", "", snippet_raw)
        snippet = re.sub(r"\s+", " ", snippet).strip()[:480]
        if not href:
            continue
        hits.append(
            SearchHit(
                title=title or href[:80],
                url=href,
                snippet=snippet,
                source_label="duckduckgo_html",
            )
        )
    return hits


def _web_search_provider_order() -> list[str]:
    """웹 검색 엔진 순서 — SearXNG(자체) → DuckDuckGo HTML(키 불필요)."""
    provider = os.getenv("IRIS_SEARCH_PROVIDER", "local").strip().lower()
    _default = ["searxng", "duckduckgo_html"]
    if provider in ("local", "auto", ""):
        return list(_default)
    if provider == "searxng":
        return ["searxng", "duckduckgo_html"]
    if provider == "duckduckgo":
        return ["duckduckgo_html", "searxng"]
    # 레거시 brave/tavily 값은 무시하고 무료 경로만 사용
    return list(_default)


def fetch_web_api_hits(query: str, *, max_results: int = 6) -> tuple[List[SearchHit], str]:
    """SearXNG → DDG HTML 순으로 시도 (유료 검색 API 미사용)."""
    for name in _web_search_provider_order():
        if name == "duckduckgo_html":
            hits = fetch_duckduckgo_hits(query, max_results=max_results)
            label = "duckduckgo_html"
        else:
            hits = fetch_searxng_hits(query, max_results=max_results)
            label = "searxng"
        if not hits:
            continue
        if hits[0].source_label == "provider_error":
            continue
        return hits, label
    return [], ""


def _playwright_fallback_enabled() -> bool:
    return _env_bool("IRIS_SEARCH_PLAYWRIGHT_FALLBACK", True)


def research_for_intent(
    query: str,
    intent: CommandKind,
    *,
    max_pages: int = 5,
) -> tuple[List[SearchHit], str]:
    """의도별 API 리서치. 반환: (hits, provider_name)."""
    q = (query or "").strip() or "Iris"

    if intent is CommandKind.WEATHER_SEARCH:
        hits = fetch_open_meteo_hits(q)
        return hits, "open_meteo"

    if intent is CommandKind.MOVIE_SEARCH:
        hits = fetch_tmdb_hits(q, max_results=max(5, max_pages))
        return hits, "tmdb"

    # NEWS / WEB / CURRENT_INFO — 웹 검색 API
    news_bias = intent is CommandKind.NEWS_SEARCH
    web_q = f"{q} news" if news_bias and "뉴스" not in q else q
    hits, provider = fetch_web_api_hits(web_q, max_results=max(6, max_pages))
    if hits:
        return hits, provider

    # SearXNG/DDG HTML이 모두 실패하면, 설정이 켜져 있을 때만 Playwright SERP 폴백 수행
    if _playwright_fallback_enabled():
        push_activity_line("Search: API empty — Playwright Google fallback.")
        from iris.agent.web_agent import fetch_research_hits as pw_fetch

        return pw_fetch(q, max_pages=max_pages), "playwright_google"

    return [
        _provider_error_hit(
            "웹 검색 불가",
            "웹 검색 수집 엔진(SearXNG/DDG HTML) 모두 실패했고, Playwright 폴백이 꺼져 있습니다(IRIS_SEARCH_PLAYWRIGHT_FALLBACK=0).",
        )
    ], "none"


def _snippet_is_substantive(snippet: str) -> bool:
    sn = (snippet or "").strip()
    if len(sn) < 10:
        return False
    low = sn.lower()
    bad = (
        "pip install playwright",
        "검색 페이지를 확인해 주세요",
        "[api 오류]",
        "api 키",
        "tmdb_api_key",
        "bearer",
    )
    return not any(b in low for b in bad)


ResearchTier = Literal["good", "partial", "poor", "failed"]


@dataclass(frozen=True)
class ResearchQuality:
    """P4 — 검색 근거 품질 점수(이진 실패 대신 degrade 단계)."""

    score: float
    tier: ResearchTier
    source_count: int
    domain_count: int
    total_snippet_chars: int
    has_provider_error: bool
    reason_ko: str


def _substantive_hits(hits: List[SearchHit]) -> list[SearchHit]:
    return [
        h
        for h in hits
        if _snippet_is_substantive(h.snippet) and not h.read_only_restricted
    ]


def _hard_failure_reason(hits: List[SearchHit]) -> str | None:
    """완전 실패(근거 0)만 True — 부분 근거는 None."""
    if not hits:
        return "검색 결과가 비어 있습니다"

    titles = {h.title for h in hits}
    if titles <= {"Playwright 미설치", "결과 없음"}:
        if "Playwright 미설치" in titles:
            return "Playwright가 설치되지 않았습니다"
        return "Google 자동 검색이 차단되었거나 결과가 없습니다"

    if all(h.source_label in ("provider_error", "error") for h in hits):
        detail = (hits[0].snippet or hits[0].title or "")[:120]
        if "키" in detail or "API" in detail:
            return "검색 API 키가 설정되지 않았거나 조회에 실패했습니다"
        return "검색 API 조회 실패"

    if not _substantive_hits(hits):
        return "가져온 페이지에 답변에 쓸 본문이 없습니다"

    return None


def _domains_from_hits(hits: Sequence[SearchHit]) -> set[str]:
    domains: set[str] = set()
    for h in hits:
        url = (h.url or "").strip()
        if not url:
            continue
        host = urlparse(url).netloc.lower()
        if host:
            domains.add(host)
    return domains


def assess_research_quality(hits: List[SearchHit]) -> ResearchQuality:
    """P4 — 출처 수·도메인 다양성·스니펫 정보량으로 0~1 점수."""
    hard = _hard_failure_reason(hits)
    substantive = _substantive_hits(hits)
    has_err = any(h.source_label in ("provider_error", "error") for h in hits)

    if hard is not None:
        return ResearchQuality(
            score=0.0,
            tier="failed",
            source_count=0,
            domain_count=0,
            total_snippet_chars=0,
            has_provider_error=has_err,
            reason_ko=hard,
        )

    n_src = len(substantive)
    domains = _domains_from_hits(substantive)
    n_dom = len(domains)
    chars = sum(len((h.snippet or "").strip()) for h in substantive)

    score = 0.0
    score += min(n_src / 4.0, 1.0) * 0.35
    score += min(n_dom / 3.0, 1.0) * 0.30
    score += min(chars / 900.0, 1.0) * 0.25
    if not has_err:
        score += 0.10
    score = round(min(max(score, 0.0), 1.0), 3)

    if score >= 0.65:
        tier: ResearchTier = "good"
        reason = ""
    elif score >= 0.38:
        tier = "partial"
        reason = "검색 근거가 일부만 확보되었습니다"
    elif score >= 0.15:
        tier = "poor"
        reason = "검색 근거가 매우 부족합니다"
    else:
        tier = "failed"
        reason = hard or "검색 근거 품질이 충분하지 않습니다"

    return ResearchQuality(
        score=score,
        tier=tier,
        source_count=n_src,
        domain_count=n_dom,
        total_snippet_chars=chars,
        has_provider_error=has_err,
        reason_ko=reason,
    )


def is_research_failure(hits: List[SearchHit]) -> tuple[bool, str]:
    """하위 호환 — tier=failed일 때만 True."""
    q = assess_research_quality(hits)
    if q.tier == "failed":
        return True, q.reason_ko
    return False, ""


def failure_user_message(reason_ko: str) -> str:
    """LlmWorker 생략 시 UI 직접 안내."""
    return (
        "지금은 검색 결과를 불러오지 못했어요.\n"
        f"원인: {reason_ko}\n"
        "다음을 확인해 주세요.\n"
        "1) .env — 날씨는 Open-Meteo(키 불필요), 영화는 TMDB_API_KEY, "
        "웹은 SearXNG(SEARXNG_BASE_URL) 또는 DuckDuckGo HTML(추가 설정 없음)\n"
        "2) IRIS_SEARCH_PLAYWRIGHT_FALLBACK=1 이면 Playwright Google SERP 폴백\n"
        "3) 인터넷 연결 · Iris 활동 로그의 Search: … 줄"
    )
