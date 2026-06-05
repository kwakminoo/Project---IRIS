"""agent 패키지."""

from iris.agent.needs_agent import (
    GEMMA_SOURCE_ONLY_INSTRUCTION,
    format_hits_for_gemma_context,
    format_hybrid_without_hits,
    research_hits_multi,
    research_hits,
    research_hits_with_intent,
)
from iris.agent.report_window import ReportWindow
from iris.agent.web_agent import (
    SearchHit,
    build_body_snippet,
    enrich_research_hits,
    extract_query_from_text,
    fetch_research_hits,
    fetch_search_hits,
    is_sensitive_url,
)

__all__ = [
    "ReportWindow",
    "SearchHit",
    "GEMMA_SOURCE_ONLY_INSTRUCTION",
    "extract_query_from_text",
    "fetch_search_hits",
    "fetch_research_hits",
    "enrich_research_hits",
    "is_sensitive_url",
    "build_body_snippet",
    "research_hits",
    "research_hits_with_intent",
    "format_hits_for_gemma_context",
]
