"""필요 자료 조사 에이전트 (web_agent 래퍼)."""

from __future__ import annotations

from typing import List

from iris.agent.web_agent import SearchHit, extract_query_from_text, fetch_search_hits


def research_hits(user_text: str) -> tuple[str, List[SearchHit]]:
    q = extract_query_from_text(user_text)
    return q, fetch_search_hits(q)
