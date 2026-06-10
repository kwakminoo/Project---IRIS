"""Frontier envelope 라우팅 — 지식 검색 vs CHAT_ONLY 회귀."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from iris.assistant.frontier_agent import _parse_frontier_envelope
from iris.assistant.router_policy import RouteLane
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.core.command_router import CommandKind
from tests.support.fakes import (
    FakeGemma,
    frontier_envelope_json,
    make_routing_assistant,
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


def test_weather_frontier_delegates_search_not_chat_stream(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    gemma.chat = lambda messages, purpose=None, **kw: frontier_envelope_json(  # type: ignore[method-assign]
        "오늘 날씨 확인해볼게요.",
        needs_execution=True,
        route=_search_route(),
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.route_user_turn") as mock_route:
        result = coord.run_turn("오늘 날씨 어때?")

    mock_route.assert_not_called()
    assert result.delegate_search is True
    assert result.delegate_frontier_stream is False
    assert result.route == RouteLane.SEARCH.value
    assert result.search_query


def test_weather_search_without_pc_execution_flag(tmp_path: Path) -> None:
    """needs_execution=false + lane=search — 검색 위임 (CHAT_ONLY 스트림 금지)."""
    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    gemma.chat = lambda messages, purpose=None, **kw: frontier_envelope_json(  # type: ignore[method-assign]
        "잠시만요.",
        needs_execution=False,
        route=_search_route(),
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("오늘 날씨 어때?")

    assert result.delegate_search is True
    assert result.delegate_frontier_stream is False


def test_hybrid_frontier_delegates_search(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    gemma.chat = lambda messages, purpose=None, **kw: frontier_envelope_json(  # type: ignore[method-assign]
        "찾아볼게요.",
        needs_execution=True,
        route={
            "intent": "search",
            "lane": "hybrid",
            "knowledge_lane": "hybrid",
            "goal": "AI 시장 전망",
            "task_type": "knowledge",
            "slots": {"query": "AI 시장 전망 2026"},
            "risk_hint": "low",
            "needs_user_confirm": False,
            "confidence": 0.88,
        },
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    result = coord.run_turn("AI 시장 전망 알려줘")

    assert result.delegate_search is True
    assert "hybrid" in (result.search_meta_json or "")


def test_greeting_still_uses_frontier_stream(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)  # type: ignore[arg-type]
    gemma.chat = lambda messages, purpose=None, **kw: frontier_envelope_json(  # type: ignore[method-assign]
        "안녕하세요!",
        needs_execution=False,
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    result = coord.run_turn("안녕")

    assert result.delegate_frontier_stream is True
    assert not result.delegate_search
