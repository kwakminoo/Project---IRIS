"""미디어·웹 재생용 URL 빌더 (CU 레시피 힌트)."""

from __future__ import annotations

from urllib.parse import quote_plus


def build_youtube_search_url(query: str) -> str:
    """YouTube 검색 결과 페이지 URL (홈이 아닌 검색 쿼리)."""
    q = (query or "").strip()
    if not q:
        raise ValueError("query가 비어 있습니다.")
    return f"https://www.youtube.com/results?search_query={quote_plus(q)}"
