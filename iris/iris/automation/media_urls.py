"""미디어·웹 재생용 URL 빌더 (CU·Media Flow 공용)."""

from __future__ import annotations

from urllib.parse import quote_plus


def build_youtube_search_url(query: str) -> str:
    """YouTube 검색 결과 페이지 URL (홈이 아닌 검색 쿼리)."""
    q = (query or "").strip()
    if not q:
        raise ValueError("query가 비어 있습니다.")
    return f"https://www.youtube.com/results?search_query={quote_plus(q)}"


def build_spotify_search_url(query: str) -> str:
    """Spotify 웹 검색 URL."""
    q = (query or "").strip()
    if not q:
        raise ValueError("query가 비어 있습니다.")
    return f"https://open.spotify.com/search/{quote_plus(q)}"


def build_netflix_search_url(query: str) -> str:
    """Netflix 검색 URL (웹 클라이언트 기준, 확장 가능 stub)."""
    q = (query or "").strip()
    if not q:
        raise ValueError("query가 비어 있습니다.")
    return f"https://www.netflix.com/search?q={quote_plus(q)}"


def build_browser_search_url(query: str) -> str:
    """플랫폼 불명 시 범용 웹 검색 URL."""
    q = (query or "").strip()
    if not q:
        raise ValueError("query가 비어 있습니다.")
    return f"https://www.google.com/search?q={quote_plus(q)}"


def build_media_open_url(platform_hint: str, search_query: str) -> str:
    """platform_hint별 검색/탐색 URL."""
    ph = (platform_hint or "unknown").strip().lower()
    if ph == "youtube":
        return build_youtube_search_url(search_query)
    if ph == "spotify":
        return build_spotify_search_url(search_query)
    if ph == "netflix":
        return build_netflix_search_url(search_query)
    return build_browser_search_url(search_query)
