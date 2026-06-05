"""search_routing — LLM slots.search_topic 매핑."""

from iris.assistant.search_routing import command_kind_for_search_slots
from iris.core.command_router import CommandKind


def test_search_topic_weather() -> None:
    assert (
        command_kind_for_search_slots({"search_topic": "weather"})
        is CommandKind.WEATHER_SEARCH
    )


def test_search_topic_default_general() -> None:
    assert command_kind_for_search_slots({}) is CommandKind.WEB_SEARCH
    assert command_kind_for_search_slots({"search_topic": "unknown"}) is CommandKind.WEB_SEARCH
