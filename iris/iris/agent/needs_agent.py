"""필요 자료 조사 에이전트 (웹 리서치 래퍼)."""

from __future__ import annotations

from typing import List, Sequence

from iris.agent.web_agent import SearchHit, extract_query_from_text, fetch_research_hits
from iris.core.command_router import CommandKind

# Gemma에 전달하는 출처 기반 답변 규칙
GEMMA_SOURCE_ONLY_INSTRUCTION = (
    "아래 [웹 리서치 출처]에 실제로 적힌 내용만 근거로 사용자 질문에 한국어로 답하세요. "
    "출처에 없는 사실·수치·날짜·인명은 추측하거나 창작하지 마세요. "
    "정보가 부족하면 '출처에서 확인되지 않았습니다'라고 말하세요. "
    "[민감 페이지]로 표시된 항목은 본문이 제한되었으므로 해당 URL 내용을 단정하지 마세요."
)


def research_hits(user_text: str, *, max_pages: int = 5) -> tuple[str, List[SearchHit]]:
    q = extract_query_from_text(user_text)
    return q, fetch_research_hits(q, max_pages=max_pages)


def _query_hint_for_intent(
    user_text: str,
    intent: CommandKind,
    *,
    slot_query: str | None = None,
) -> str:
    """의도별로 검색어에 맥락 키워드를 덧붙여 검색 품질을 높인다."""
    # Phase 3: Unified/LLM 라우터가 준 slots.query 우선 (regex 추출 폴백)
    if slot_query and str(slot_query).strip():
        base = str(slot_query).strip()
    else:
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


def research_hits_with_intent(
    user_text: str,
    intent: CommandKind,
    *,
    max_pages: int = 5,
    slot_query: str | None = None,
) -> tuple[str, List[SearchHit]]:
    """Intent Router 검색 의도 → SERP + 상위 페이지 본문 리서치."""
    q = _query_hint_for_intent(user_text, intent, slot_query=slot_query)
    return q, fetch_research_hits(q, max_pages=max_pages)


def format_hits_for_gemma_context(
    query: str,
    hits: Sequence[SearchHit],
    *,
    intent_label: str,
) -> str:
    """리서치 출처를 Gemma 시스템 컨텍스트 블록으로 직렬화."""
    lines = [
        f"[웹 리서치 출처 | 의도={intent_label} | 검색어={query}]",
        GEMMA_SOURCE_ONLY_INSTRUCTION,
        "",
    ]
    for i, h in enumerate(hits, 1):
        snip = (h.snippet or "").strip()
        lines.append(f"--- 출처 {i} ---")
        lines.append(f"제목: {h.title}")
        lines.append(f"URL: {h.url}")
        if h.date_candidate:
            lines.append(f"날짜 후보: {h.date_candidate}")
        if h.read_only_restricted:
            lines.append("상태: [민감 페이지] 본문 추출 제한")
        if snip:
            lines.append(f"요약 스니펫: {snip}")
        lines.append("")
    return "\n".join(lines).strip()
