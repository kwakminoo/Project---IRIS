"""Frontier envelope 라우팅 — 지식 검색 vs CHAT_ONLY 회귀."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from iris.assistant.frontier_agent import _parse_frontier_envelope
from iris.assistant.route_analysis import OperationKind, RouteAnalysis, RouteOperation
from iris.assistant.router_policy import RouteLane
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.core.command_router import CommandKind
from tests.support.fakes import (
    FakeGemma,
    frontier_envelope_json,
    make_routing_assistant,
)


def _search_analysis(query: str = "검색") -> RouteAnalysis:
    return RouteAnalysis(
        primary_goal=query,
        operations=(
            RouteOperation("op-1", OperationKind.SEARCH, query, "web.search", query),
            RouteOperation(
                "op-2",
                OperationKind.RESPOND,
                "답변",
                None,
                None,
                depends_on=("op-1",),
            ),
        ),
        requires_user_response=True,
        requires_search=True,
        requires_execution=False,
        requires_monitoring=False,
        contains_conditional_flow=False,
        contains_cross_capability_flow=False,
        requested_capabilities=("web.search",),
        confidence=0.9,
    )


def _search_route(**slot_overrides: object) -> dict[str, object]:
    slots: dict[str, object] = {
        "query": "서울 오늘 날씨",
        "search_topic": "weather",
    }
    slots.update(slot_overrides)
    return {
        "intent": "search",
        "lane": "search",
        "knowledge_lane": "search",
        "goal": "오늘 날씨 안내",
        "task_type": "knowledge",
        "slots": slots,
        "risk_hint": "low",
        "needs_user_confirm": False,
        "clarification": None,
        "confidence": 0.9,
    }


def test_parse_accepts_search_lane_with_needs_execution_false() -> None:
    """지식 검색은 PC 실행 플래그 없이도 envelope 허용."""
    data = json.loads(
        frontier_envelope_json(
            "날씨 확인해볼게요.",
            needs_execution=False,
            route=_search_route(),
        )
    )
    parsed = _parse_frontier_envelope(data, "오늘 날씨 어때?", [], min_confidence=0.65)
    assert parsed is not None
    assert parsed.routed_turn.lane is RouteLane.SEARCH
    assert parsed.routed_turn.kind is CommandKind.WEATHER_SEARCH


def test_parse_rejects_pc_lane_with_needs_execution_false() -> None:
    data = json.loads(
        frontier_envelope_json(
            "메모장 열게요.",
            needs_execution=False,
            route={
                "intent": "computer_use",
                "lane": "computer_use",
                "knowledge_lane": "chat_only",
                "goal": "메모장",
                "task_type": "open_app",
                "slots": {},
                "risk_hint": "low",
                "needs_user_confirm": False,
                "confidence": 0.9,
            },
        )
    )
    assert _parse_frontier_envelope(data, "메모장", [], min_confidence=0.65) is None


def test_parse_rejects_chat_only_with_needs_execution_true() -> None:
    data = json.loads(
        frontier_envelope_json(
            "안녕!",
            needs_execution=True,
            route={
                "intent": "chat",
                "lane": "chat_only",
                "knowledge_lane": "chat_only",
                "goal": "",
                "task_type": "unknown",
                "slots": {},
                "risk_hint": "low",
                "needs_user_confirm": False,
                "confidence": 0.9,
            },
        )
    )
    assert _parse_frontier_envelope(data, "안녕", [], min_confidence=0.65) is None


def test_weather_unified_delegates_search_not_chat_stream(tmp_path: Path) -> None:
    from iris.assistant.router_policy import RoutedTurn

    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    routed = RoutedTurn(
        kind=CommandKind.WEATHER_SEARCH,
        lane=RouteLane.SEARCH,
        slots={"query": "서울 오늘 날씨", "search_topic": "weather"},
        knowledge_lane="search",
        route_analysis=_search_analysis("서울 오늘 날씨"),
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=routed,
    ), patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        result = coord.run_turn("오늘 날씨 어때?")

    mock_f.assert_not_called()
    assert result.delegate_search is True
    assert result.delegate_frontier_stream is False
    assert result.route == RouteLane.SEARCH.value
    assert result.search_query


def test_weather_search_without_pc_execution_flag(tmp_path: Path) -> None:
    """hybrid — Unified SEARCH 위임 (CHAT_ONLY 스트림 금지)."""
    from iris.assistant.router_policy import RoutedTurn

    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    routed = RoutedTurn(
        kind=CommandKind.WEATHER_SEARCH,
        lane=RouteLane.SEARCH,
        slots={"query": "서울 오늘 날씨", "search_topic": "weather"},
        knowledge_lane="search",
        route_analysis=_search_analysis("서울 오늘 날씨"),
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=routed,
    ):
        result = coord.run_turn("오늘 날씨 어때?")

    assert result.delegate_search is True
    assert result.delegate_frontier_stream is False


def test_hybrid_unified_delegates_search(tmp_path: Path) -> None:
    from iris.assistant.router_policy import RoutedTurn

    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    routed = RoutedTurn(
        kind=CommandKind.WEB_SEARCH,
        lane=RouteLane.HYBRID,
        slots={"query": "AI 시장 전망 2026"},
        knowledge_lane="hybrid",
        route_analysis=_search_analysis("AI 시장 전망 2026"),
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=routed,
    ), patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        result = coord.run_turn("AI 시장 전망 알려줘")

    mock_f.assert_not_called()
    assert result.delegate_search is True
    assert "hybrid" in (result.search_meta_json or "")


def test_greeting_uses_fast_dialogue_stream(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        result = coord.run_turn("안녕")

    mock_f.assert_not_called()
    assert result.delegate_dialogue_stream is True
    assert not result.delegate_frontier_stream
    assert not result.delegate_search
