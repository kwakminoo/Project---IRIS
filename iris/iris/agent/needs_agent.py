"""필요 자료 조사 에이전트 (web_agent 래퍼)."""

from __future__ import annotations

from typing import List, Sequence

from iris.agent.web_agent import SearchHit, extract_query_from_text, fetch_search_hits
from iris.core.command_router import CommandKind


def research_hits(user_text: str) -> tuple[str, List[SearchHit]]:
    q = extract_query_from_text(user_text)
    return q, fetch_search_hits(q)


def _query_hint_for_intent(user_text: str, intent: CommandKind) -> str:
    """의도별로 검색어에 맥락 키워드를 덧붙여 검색 품질을 높인다."""
    base = extract_query_from_text(user_text).strip() or user_text.strip()
    if intent is CommandKind.MOVIE_SEARCH:
        return f"{base} 영화 개봉 상영 2026"
    if intent is CommandKind.NEWS_SEARCH:
        return f"{base} 뉴스"
    if intent is CommandKind.WEATHER_SEARCH:
        return f"{base} 날씨 예보"
    if intent is CommandKind.CURRENT_INFO_SEARCH:
        return f"{base} 최신 정보"
    return base


def research_hits_with_intent(user_text: str, intent: CommandKind) -> tuple[str, List[SearchHit]]:
    """Intent Router가 분류한 검색 의도에 맞춰 웹 검색을 수행한다."""
    q = _query_hint_for_intent(user_text, intent)
    return q, fetch_search_hits(q)


def format_hits_for_gemma_context(
    query: str,
    hits: Sequence[SearchHit],
    *,
    intent_label: str,
) -> str:
    """검색 결과를 Gemma 시스템 컨텍스트 블록으로 직렬화한다."""
    lines = [
        f"[웹 검색 도구 결과 | 의도={intent_label} | 검색어={query}]",
        "아래 목록만 근거로 사용자 질문에 한국어로 답하세요. 없는 내용은 추측하지 마세요.",
        "",
    ]
    for i, h in enumerate(hits, 1):
        snip = (h.snippet or "").strip()
        lines.append(f"{i}. {h.title}\n   URL: {h.url}")
        if snip:
            lines.append(f"   요약: {snip}")
    return "\n".join(lines)
