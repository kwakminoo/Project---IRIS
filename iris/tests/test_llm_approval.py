"""LLM 승인 분류·pending_cu — TurnCoordinator 경로 (현재 API 기준)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from iris.assistant.llm_approval import (
    FollowupClassification,
    FollowupDecision,
    classify_user_followup,
    classify_user_followup_rule,
    is_rule_approval,
    resolve_followup_for_pending,
)
from iris.assistant.router_policy import RouteLane, RoutedTurn
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.core.command_router import CommandKind
from iris.core.context_manager import PendingComputerUseGoal
from tests.support.fakes import ApprovalGemma, FakeGemma, make_test_assistant


def test_rule_approval_progress_phrase() -> None:
    assert is_rule_approval("진행해줘")
    cls = classify_user_followup_rule("진행해줘")
    assert cls.decision is FollowupDecision.APPROVE


def test_llm_approval_colloquial_approve() -> None:
    gemma = ApprovalGemma("approve")
    for phrase in ("어 해줘", "그럼 해"):
        cls = classify_user_followup(
            phrase,
            "이 작업을 진행하려면 확인이 필요합니다. 진행할까요?",
            gemma,  # type: ignore[arg-type]
            use_llm=True,
        )
        assert cls.decision is FollowupDecision.APPROVE, phrase


def test_critical_pending_uses_llm_not_rule_only() -> None:
    gemma = ApprovalGemma("approve")
    cls = resolve_followup_for_pending(
        "어",
        "셸 명령을 실행하려면 확인이 필요합니다.",
        gemma,  # type: ignore[arg-type]
        force_rule_only=False,
        use_llm=True,
    )
    assert cls.decision is FollowupDecision.APPROVE
    assert len(gemma.calls) == 1


def test_pending_cu_tool_approve_resumes_cu_loop(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_test_assistant(tmp_path, gemma)
    assistant.ctx.pending_cu = PendingComputerUseGoal(
        goal="메모장 켜줘",
        risk_hint="critical",
        prompt="이 작업을 진행하려면 확인이 필요합니다. 진행할까요?\n- 셸 명령 실행",
        pending_tool_name="run_shell",
        pending_tool_params={"command": "notepad"},
        pending_tool_preview="쉘 실행: notepad",
        cu_mode="step_planner",
        pending_plan_index=1,
        cu_observations=["goal: 메모장 켜줘"],
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch(
        "iris.assistant.turn_coordinator.resolve_followup_for_pending",
        return_value=FollowupClassification(FollowupDecision.APPROVE, 0.95),
    ):
        with patch.object(
            assistant,
            "run_computer_use_resume",
            return_value="Iris: 메모장을 열고 작업을 마쳤습니다.",
        ) as mock_resume:
            with patch.object(assistant, "run_pending_cu_tool") as mock_tool:
                result = coord.run_turn("어 해줘")

    mock_resume.assert_called_once()
    mock_tool.assert_not_called()
    assert assistant.ctx.pending_cu is None
    assert result.executed is True
    assert "마쳤" in result.user_visible


def test_pending_cu_approve_runs_cu_once(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_test_assistant(tmp_path, gemma)
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
    gemma = FakeGemma()
    assistant = make_test_assistant(tmp_path, gemma)
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
                "iris.assistant.turn_coordinator.route_user_turn",
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
