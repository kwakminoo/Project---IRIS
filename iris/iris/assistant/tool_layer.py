"""Tool Layer — Gemma 4 이전 의도 분류 후 호출되는 도구(웹 검색, 자동화 등).

로컬 Gemma가 기본이며, 외부 LLM API는 기본 경로에 포함하지 않는다.
"""

from __future__ import annotations

from iris.core.command_router import CommandKind

# 웹 검색 에이전트(Playwright)로 위임 후 Gemma가 결과를 요약하는 의도들
SEARCH_COMMAND_KINDS: frozenset[CommandKind] = frozenset(
    {
        CommandKind.WEB_SEARCH,
        CommandKind.CURRENT_INFO_SEARCH,
        CommandKind.MOVIE_SEARCH,
        CommandKind.NEWS_SEARCH,
        CommandKind.WEATHER_SEARCH,
    }
)


def is_search_intent(kind: CommandKind) -> bool:
    return kind in SEARCH_COMMAND_KINDS
