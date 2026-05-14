"""agent 패키지."""

from iris.agent.needs_agent import format_hits_for_gemma_context, research_hits, research_hits_with_intent
from iris.agent.report_window import ReportWindow
from iris.agent.web_agent import SearchHit, extract_query_from_text, fetch_search_hits

__all__ = [
    "ReportWindow",
    "SearchHit",
    "extract_query_from_text",
    "fetch_search_hits",
    "research_hits",
    "research_hits_with_intent",
    "format_hits_for_gemma_context",
]
