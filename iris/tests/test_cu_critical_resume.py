"""CRITICAL 승인 후 Computer Use 루프 재개 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.core.context_manager import PendingComputerUseGoal
from iris.storage.database import Database


def _sample_full_plan_json() -> str:
    return json.dumps(
        {
            "goal": "메모장을 열고 hello 입력",
            "plan_id": "test-plan-resume",
            "plans": [
                {
                    "index": 0,
                    "tool": "list_open_windows",
                    "params": {},
                    "reason": "창 확인",
                    "checkpoint_id": None,
                },
                {
                    "index": 1,
                    "tool": "launch_app",
                    "params": {"app_key": "notepad", "display_name": "메모장"},
                    "reason": "메모장 실행",
                    "checkpoint_id": "cp_app_open",
                },
                {
                    "index": 2,
                    "tool": "focus_window",
                    "params": {"title_sub": "메모장"},
                    "reason": "메모장 포커스",
                    "checkpoint_id": "cp_focus",
                },
                {
                    "index": 3,
                    "tool": "type_text",
                    "params": {"text": "hello"},
                    "reason": "텍스트 입력",
                    "checkpoint_id": "cp_text_typed",
                },
                {
                    "index": 4,
                    "tool": "perceive_desktop",
                    "params": {},
                    "reason": "완료 확인",
                    "checkpoint_id": "cp_final",
                },
            ],
            "expected_checkpoints": [
                "cp_app_open",
                "cp_focus",
                "cp_text_typed",
                "cp_final",
            ],
            "confidence": 0.85,
        },
        ensure_ascii=False,
    )


def _make_assistant(tmp_path: Path) -> IrisAssistant:
    db = Database(path=tmp_path / "cu_resume.db")
    executor = ActionExecutor(db, {})
    settings = SimpleNamespace(
        computer_use_full_plan_enabled=True,
        computer_use_input_notify_delay_seconds=0.5,
        tts_enable_speech_formatter=False,
    )
    gemma = MagicMock()
    return IrisAssistant(db, executor, gemma, {}, settings)  # type: ignore[arg-type]


def test_resume_after_critical_runs_tool_and_continues_full_plan(tmp_path: Path) -> None:
    """run_shell 승인 → 해당 step 실행 → checkpoint verify → loop continue."""
    assistant = _make_assistant(tmp_path)
    registry = assistant._executor.tool_registry
    plan = json.loads(_sample_full_plan_json())
    # full_plan 스냅샷은 launch_app 유지 — 승인된 run_shell은 pending_tool로 별도 실행

    pending = PendingComputerUseGoal(
        goal=plan["goal"],
        risk_hint="critical",
        prompt="셸 명령 승인 필요",
        slots={},
        pending_tool_name="run_shell",
        pending_tool_params={"command": "echo iris-test"},
        pending_tool_preview="쉘: echo iris-test",
        cu_mode="full_plan",
        executed_through_index=0,
        pending_plan_index=1,
        pending_checkpoint_id="cp_app_open",
        full_plan_snapshot=plan,
        cu_observations=["goal: 메모장", "tool_ok: list_open_windows ok"],
    )

    agent = ComputerUseAgent(
        assistant,
        assistant._gemma,
        registry,
        max_steps=10,
    )

    shell_result = AutomationToolResult(True, "셸 실행 완료", "ok")
    perceive_results = [
        AutomationToolResult(True, "창", "w"),
        AutomationToolResult(True, "창", "w"),
    ]

    def _registry_run(tool_name: str, ctx: object) -> AutomationToolResult:
        if tool_name == "run_shell":
            return shell_result
        if tool_name == "focus_window":
            return AutomationToolResult(True, "포커스", "ok")
        if tool_name == "type_text":
            return AutomationToolResult(True, "입력", "ok|ok")
        if tool_name in ("perceive_desktop", "list_open_windows", "uia_snapshot"):
            return perceive_results.pop(0) if perceive_results else AutomationToolResult(
                True, "창", "w"
            )
        return AutomationToolResult(True, tool_name, "ok")

    registry.run = MagicMock(side_effect=_registry_run)  # type: ignore[method-assign]

    def _mark_success(ctx: object, **kwargs: object) -> str:
        from iris.assistant.computer_use_agent import ComputerUseContext

        if isinstance(ctx, ComputerUseContext):
            ctx.done = True
            ctx.final_message = "작업을 완료했습니다."
        return "success"

    with patch.object(
        agent,
        "_run_checkpoint_verify",
        return_value=True,
    ) as mock_verify:
        with patch.object(
            agent,
            "_iterate_full_plan_items",
            side_effect=_mark_success,
        ) as mock_continue:
            msg = agent.resume_after_critical_approval(pending)

    shell_calls = [c for c in registry.run.call_args_list if c[0][0] == "run_shell"]
    assert len(shell_calls) == 1
    assert shell_calls[0][0][1].approved is True
    mock_verify.assert_called_once()
    mock_continue.assert_called_once()
    assert mock_continue.call_args.kwargs.get("start_after_index") == 1
    assert "완료" in msg

    sess = assistant.memory.load_task_session()
    assert "approved:run_shell" in (sess.get("approvals") or [])
