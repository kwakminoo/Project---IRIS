"""LLM 승인 분류·pending_cu 테스트."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import patch

from iris.ai.gemma_client import ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.llm_approval import (
    FollowupClassification,
    FollowupDecision,
    classify_user_followup_rule,
    is_rule_approval,
)
from iris.assistant.router_policy import RouteLane, RoutedTurn
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.automation.action_executor import ActionExecutor
from iris.core.command_router import CommandKind
from iris.core.context_manager import PendingComputerUseGoal
from iris.storage.database import Database


class _FakeGemma:
    def __init__(self) -> None:
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        return "반가워요!"


def _make_assistant(tmp_path: Path, gemma: _FakeGemma) -> IrisAssistant:
    db = Database(path=tmp_path / "approval.db")
    executor = ActionExecutor(db, {})
    settings = SimpleNamespace(
        llm_intent_router_enabled=False,
        llm_approval_enabled=True,
        tts_enable_speech_formatter=False,
    )
    return IrisAssistant(db, executor, gemma, {}, settings)  # type: ignore[arg-type]


def test_rule_approval_progress_phrase() -> None:
    assert is_rule_approval("진행해줘")
    cls = classify_user_followup_rule("진행해줘")
    assert cls.decision is FollowupDecision.APPROVE


def test_pending_cu_approve_runs_cu_once(tmp_path: Path) -> None:
    gemma = _FakeGemma()
    assistant = _make_assistant(tmp_path, gemma)
    assistant.ctx.pending_cu = PendingComputerUseGoal(
        goal="카톡 열고 철수에게 안녕 보내",
        risk_hint="low",
        prompt="진행할까요?",
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 메시지를 보냈습니다.",
    ) as mock_cu:
        result = coord.run_turn("진행해줘")

    mock_cu.assert_called_once()
    assert mock_cu.call_args.kwargs.get("goal") == "카톡 열고 철수에게 안녕 보내"
    assert assistant.ctx.pending_cu is None
    assert result.route == RouteLane.COMPUTER_USE.value
    assert "보냈" in result.user_visible


def test_unrelated_followup_clears_pending_no_cu(tmp_path: Path) -> None:
    gemma = _FakeGemma()
    assistant = _make_assistant(tmp_path, gemma)
    original_goal = "셸로 로그 지워"
    assistant.ctx.pending_cu = PendingComputerUseGoal(
        goal=original_goal,
        risk_hint="low",
        prompt="진행할까요?",
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch(
        "iris.assistant.turn_coordinator.resolve_followup_for_pending",
        return_value=FollowupClassification(FollowupDecision.UNRELATED, 0.9),
    ):
        with patch.object(assistant, "run_computer_use_loop") as mock_cu:
            with patch(
                "iris.assistant.turn_coordinator.resolve_route_lane",
                return_value=RoutedTurn(
                    kind=CommandKind.GENERAL_CHAT,
                    lane=RouteLane.CHAT_ONLY,
                    goal="오늘 날씨 알려줘",
                ),
            ):
                result = coord.run_turn("오늘 날씨 어때")

    assert assistant.ctx.pending_cu is None
    mock_cu.assert_not_called()
    assert result.route == RouteLane.CHAT_ONLY.value
    assert original_goal not in (result.user_visible or "")
