"""웹 검색 의도 — LLM slots 기반 CommandKind 매핑 (휴리스틱 regex 대신)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from iris.core.command_router import CommandKind

# Unified/Intent Router slots.search_topic → 검색 세부 의도
_SEARCH_TOPIC_KIND: dict[str, CommandKind] = {
    "general": CommandKind.WEB_SEARCH,
    "web": CommandKind.WEB_SEARCH,
    "weather": CommandKind.WEATHER_SEARCH,
    "news": CommandKind.NEWS_SEARCH,
    "movie": CommandKind.MOVIE_SEARCH,
    "current_info": CommandKind.CURRENT_INFO_SEARCH,
    "latest": CommandKind.CURRENT_INFO_SEARCH,
    "comparison": CommandKind.WEB_SEARCH,
    "definition": CommandKind.WEB_SEARCH,
}


def command_kind_for_search_slots(slots: Mapping[str, Any] | None) -> CommandKind:
    """LLM이 준 search_topic으로 검색 CommandKind 결정. 없으면 일반 웹 검색."""
    if not slots:
        return CommandKind.WEB_SEARCH
    raw = slots.get("search_topic") or slots.get("search_kind")
    topic = str(raw).strip().lower() if raw is not None else ""
    if not topic:
        return CommandKind.WEB_SEARCH
    return _SEARCH_TOPIC_KIND.get(topic, CommandKind.WEB_SEARCH)
