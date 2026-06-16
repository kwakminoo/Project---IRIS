"""Frontier envelope·TurnCoordinator 연동 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from iris.assistant.frontier_agent import run_frontier_turn
from iris.assistant.router_policy import RouteLane
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.ui.workers import AgentWorker
from iris.assistant.unified_router import envelope_route_to_routed_turn
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext, DialogueStep
from tests.support.fakes import (
    FakeGemma,
    frontier_envelope_json,
    make_routing_assistant,
    make_test_assistant,
    unified_router_json,
)


def test_envelope_route_to_routed_turn_chat_only() -> None:
    raw = json.loads(
        unified_router_json(intent="chat", lane="chat_only", goal="인사")
    )
    routed = envelope_route_to_routed_turn(raw, "안녕", [])
    assert routed is not None
    assert routed.lane is RouteLane.CHAT_ONLY
    assert routed.kind is CommandKind.GENERAL_CHAT


def test_frontier_chat_only_no_unified_router(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "frontier_enabled": True,
            "unified_llm_router_enabled": True,
            "router_mode": "frontier_first",
            "chat_fast_path_enabled": False,
        },
    )
    gemma.chat = lambda messages, purpose=None, **kw: frontier_envelope_json(  # type: ignore[method-assign]
        "반가워요!",
        needs_execution=False,
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.route_user_turn") as mock_route:
        result = coord.run_turn("안녕")

    mock_route.assert_not_called()
    assert result.delegate_frontier_stream is True
    assert result.frontier_reply == "반가워요!"
    assert result.delegate_dialogue_stream is False


def test_frontier_chat_only_skips_prefetch_callback(tmp_path: Path) -> None:
    """CHAT_ONLY — on_frontier_reply 없이 delegate만 (UI 이중 재생 방지)."""
    gemma = FakeGemma()
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "router_mode": "frontier_first",
            "chat_fast_path_enabled": False,
        },
    )
    gemma.chat = lambda messages, purpose=None, **kw: frontier_envelope_json(  # type: ignore[method-assign]
        "안녕하세요.",
        needs_execution=False,
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    prefetch_calls: list[str] = []

    with patch("iris.assistant.turn_coordinator.route_user_turn") as mock_route:
        result = coord.run_turn("안녕", on_frontier_reply=prefetch_calls.append)

    mock_route.assert_not_called()
    assert prefetch_calls == []
    assert result.delegate_frontier_stream is True
    assert result.frontier_reply == "안녕하세요."
    assert "frontier_reply_callback" not in result.logs


def test_worker_frontier_chat_only_emits_stream_once(tmp_path: Path) -> None:
    """AgentWorker — CHAT_ONLY frontier_stream 1회(store_history=True)만."""
    gemma = FakeGemma()
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "router_mode": "frontier_first",
            "chat_fast_path_enabled": False,
        },
    )
    gemma.chat = lambda messages, purpose=None, **kw: frontier_envelope_json(  # type: ignore[method-assign]
        "안녕하세요.",
        needs_execution=False,
    )
    worker = AgentWorker(assistant, "안녕")  # type: ignore[arg-type]
    streams: list[tuple[str, bool]] = []
    worker.frontier_stream.connect(
        lambda reply, store_history: streams.append((reply, store_history))
    )

    with patch("iris.assistant.turn_coordinator.route_user_turn") as mock_route:
        worker.run()

    mock_route.assert_not_called()
    assert streams == [("안녕하세요.", True)]


def test_frontier_parse_fail_falls_back_to_unified_router(tmp_path: Path) -> None:
    gemma = FakeGemma(chat_reply="not json")
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "frontier_enabled": True,
            "unified_llm_router_enabled": True,
            "router_mode": "frontier_first",
            "chat_fast_path_enabled": False,
        },
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    fallback = envelope_route_to_routed_turn(
        json.loads(unified_router_json(intent="chat", lane="chat_only")),
        "안녕",
        [],
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=fallback,
    ) as mock_route:
        result = coord.run_turn("안녕")

    mock_route.assert_called_once()
    assert result.delegate_frontier_stream is False
    assert result.delegate_dialogue_stream is True


def test_frontier_cu_skips_completion_in_reply(tmp_path: Path) -> None:
    reply = frontier_envelope_json(
        "메모장 실행을 시도할게요.",
        needs_execution=True,
        route={
            "intent": "computer_use",
            "lane": "computer_use",
            "goal": "메모장 실행",
            "task_type": "open_app",
            "slots": {},
            "risk_hint": "low",
            "needs_user_confirm": False,
            "confidence": 0.9,
        },
    )
    gemma = FakeGemma(chat_reply=reply)
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "frontier_enabled": True,
            "router_mode": "frontier_first",
            "chat_fast_path_enabled": False,
        },
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    frontier_calls: list[str] = []

    with patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 메모장을 열었습니다.",
    ) as mock_cu:
        coord.run_turn(
            "메모장 켜줘",
            on_frontier_reply=frontier_calls.append,
        )

    mock_cu.assert_called_once()
    assert frontier_calls == ["메모장 실행을 시도할게요."]
    assert "열었습니다" not in frontier_calls[0]


def test_multi_turn_active_skips_frontier(tmp_path: Path) -> None:
    gemma = FakeGemma(chat_reply=frontier_envelope_json("hi"))
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "frontier_enabled": True,
            "unified_llm_router_enabled": True,
        },
    )
    assistant.ctx.step = DialogueStep.WORK_ASK_TASK
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    from iris.assistant.router_policy import RoutedTurn

    with patch("iris.assistant.turn_coordinator.route_user_turn") as mock_route:
        mock_route.return_value = RoutedTurn(
            kind=CommandKind.WORK_MODE,
            lane=RouteLane.MULTI_TURN,
        )
        coord.run_turn("개발 이어갈게")

    frontier_calls = [c for c in gemma.calls if c and "Frontier" in c[0].content]
    assert len(frontier_calls) == 0
    mock_route.assert_called_once()


def test_run_frontier_turn_low_confidence_returns_none(tmp_path: Path) -> None:
    gemma = FakeGemma(
        chat_reply=frontier_envelope_json("안녕", confidence=0.2),
    )
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={"frontier_min_confidence": 0.65},
    )
    ctx = DialogueContext()
    result = run_frontier_turn("안녕", ctx, gemma, assistant=assistant)  # type: ignore[arg-type]
    assert result is None
