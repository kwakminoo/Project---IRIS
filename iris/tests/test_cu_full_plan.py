"""Computer Use 전체 플랜(CU_FULL_PLAN_PLANNER) 파싱·실행 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import MagicMock, patch

from iris.ai.gemma_client import ChatMessage
from iris.assistant.action_plan import parse_computer_use_full_plan
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.assistant.cu_prompts import CU_FULL_PLAN_PLANNER_SYSTEM
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.storage.database import Database


def _sample_full_plan_json() -> str:
    return json.dumps(
        {
            "goal": "메모장을 열고 hello 입력",
            "plan_id": "test-plan-1",
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


def test_parse_computer_use_full_plan_valid() -> None:
    plan = parse_computer_use_full_plan(_sample_full_plan_json())
    assert plan is not None
    assert plan.plan_id == "test-plan-1"
    assert len(plan.plans) == 5
    assert plan.plans[1].checkpoint_id == "cp_app_open"
    assert plan.plans[4].tool == "perceive_desktop"


def test_parse_computer_use_full_plan_rejects_run_shell() -> None:
    raw = _sample_full_plan_json()
    data = json.loads(raw)
    data["plans"][1]["tool"] = "run_shell"
    assert parse_computer_use_full_plan(json.dumps(data)) is None


def test_parse_computer_use_full_plan_short_without_checkpoints() -> None:
    raw = json.dumps(
        {
            "goal": "메모장 열기",
            "plan_id": "short-1",
            "plans": [
                {
                    "index": 0,
                    "tool": "launch_app",
                    "params": {"app_key": "notepad"},
                    "reason": "실행",
                },
                {
                    "index": 1,
                    "tool": "focus_window",
                    "params": {"title_sub": "메모장"},
                    "reason": "포커스",
                },
            ],
            "expected_checkpoints": [],
            "confidence": 0.7,
        },
        ensure_ascii=False,
    )
    plan = parse_computer_use_full_plan(raw)
    assert plan is not None
    assert len(plan.plans) == 2
    assert plan.plans[0].checkpoint_id is None


def test_parse_computer_use_full_plan_rejects_single_step() -> None:
    raw = json.dumps(
        {
            "goal": "메모장",
            "plan_id": "one",
            "plans": [
                {
                    "index": 0,
                    "tool": "launch_app",
                    "params": {"app_key": "notepad"},
                    "reason": "실행",
                }
            ],
            "expected_checkpoints": [],
            "confidence": 0.5,
        },
        ensure_ascii=False,
    )
    assert parse_computer_use_full_plan(raw) is None


def test_parse_computer_use_full_plan_ask_user_only() -> None:
    raw = json.dumps(
        {
            "goal": "검색어 필요",
            "plan_id": "ask-1",
            "plans": [
                {
                    "index": 0,
                    "tool": "ask_user",
                    "params": {"question": "무엇을 검색할까요?"},
                    "reason": "search_query 없음",
                    "checkpoint_id": None,
                }
            ],
            "expected_checkpoints": [],
            "confidence": 0.2,
        },
        ensure_ascii=False,
    )
    plan = parse_computer_use_full_plan(raw)
    assert plan is not None
    assert len(plan.plans) == 1
    assert plan.plans[0].tool == "ask_user"


class _FullPlanGemma:
    def __init__(self, full_plan_json: str) -> None:
        self._full_plan_json = full_plan_json
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        if messages and "전체 플랜 계획기" in messages[0].content:
            return self._full_plan_json
        if messages and "체크포인트 검증기" in messages[0].content:
            return json.dumps(
                {
                    "checkpoint_id": "cp_final",
                    "achieved": True,
                    "failure_kind": "unknown",
                    "progress_summary": "hello 입력 확인",
                    "gap": "",
                    "last_ok_index": 4,
                    "resume_from_index": 5,
                    "confidence": 0.9,
                },
                ensure_ascii=False,
            )
        if messages and "Repair 계획기" in messages[0].content:
            return json.dumps(
                {
                    "plan_id": "test-plan-1",
                    "repair_attempt": 1,
                    "gap": "",
                    "repair_steps": [],
                    "recommend_fail": False,
                    "ask_user": None,
                },
                ensure_ascii=False,
            )
        return '{"tool": "step_failed", "params": {}, "reason": "폴백"}'


def _perceive_ok() -> AutomationToolResult:
    return AutomationToolResult(
        True,
        "perceive: ocr | Notepad | hello",
        '{"perception_source":"ocr","active_window":"Notepad"}',
    )


def test_full_plan_session_executes_plans(tmp_path: Path) -> None:
    gemma = _FullPlanGemma(_sample_full_plan_json())
    settings = SimpleNamespace(computer_use_full_plan_enabled=True)
    db = Database(path=tmp_path / "fp.db")
    assistant = IrisAssistant(db, ActionExecutor(db, {}), gemma, {}, settings=settings)  # type: ignore[arg-type]
    registry = assistant._executor.tool_registry

    def _tool_side_effect(name: str, ctx: object) -> AutomationToolResult:
        if name == "perceive_desktop":
            return _perceive_ok()
        if name == "list_open_windows":
            return AutomationToolResult(True, "windows", "Notepad | 메모장")
        return AutomationToolResult(True, f"{name} ok", "detail")

    registry.run = MagicMock(side_effect=_tool_side_effect)  # type: ignore[method-assign]

    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=20)  # type: ignore[arg-type]
    slots = {
        "text_to_type": "hello",
        "app_key": "notepad",
        "display_name": "메모장",
    }
    with patch(
        "iris.assistant.cu_mechanical_verify.read_focused_field_text",
        return_value=(True, "hello"),
    ):
        msg = agent.run("메모장에 hello 적어줘", slots=slots)

    assert "hello" in msg or "완료" in msg or "입력" in msg
    planner = [c for c in gemma.calls if c and "전체 플랜 계획기" in c[0].content]
    assert len(planner) == 1
    assert "초기 Perceive observation" in planner[0][1].content


def test_cu_full_plan_planner_system_contains_checkpoint_rules() -> None:
    assert "checkpoint_id" in CU_FULL_PLAN_PLANNER_SYSTEM
    assert "cp_final" in CU_FULL_PLAN_PLANNER_SYSTEM
    assert "run_shell" in CU_FULL_PLAN_PLANNER_SYSTEM


def _minimal_tool_fail_plan_json() -> str:
    return json.dumps(
        {
            "goal": "메모장 실행",
            "plan_id": "fail-plan",
            "plans": [
                {
                    "index": 0,
                    "tool": "launch_app",
                    "params": {"app_key": "notepad"},
                    "reason": "메모장 실행",
                },
                {
                    "index": 1,
                    "tool": "focus_window",
                    "params": {"title_sub": "메모장"},
                    "reason": "포커스",
                },
            ],
            "expected_checkpoints": [],
            "confidence": 0.8,
        },
        ensure_ascii=False,
    )


class _ToolFailRepairGemma:
    """tool_fail → repair exhausted → step planner 폴백 시나리오."""

    def __init__(self) -> None:
        self.calls: list[Sequence[ChatMessage]] = []
        self._repair_calls = 0

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        sys = messages[0].content if messages else ""
        if "전체 플랜 계획기" in sys:
            return _minimal_tool_fail_plan_json()
        if "Repair" in sys or "repair_steps" in sys:
            self._repair_calls += 1
            return json.dumps(
                {
                    "plan_id": "fail-plan",
                    "repair_attempt": self._repair_calls,
                    "gap": "수리 실패",
                    "repair_steps": [],
                    "recommend_fail": True,
                    "ask_user": None,
                },
                ensure_ascii=False,
            )
        if "Computer Use 플래너" in sys:
            return json.dumps(
                {"tool": "step_complete", "params": {}, "reason": "폴백 완료"},
                ensure_ascii=False,
            )
        if "체크포인트 검증기" in sys:
            return json.dumps(
                {
                    "checkpoint_id": "cp_final",
                    "achieved": False,
                    "failure_kind": "unknown",
                    "progress_summary": "",
                    "gap": "미달성",
                    "last_ok_index": -1,
                    "resume_from_index": 0,
                    "confidence": 0.1,
                },
                ensure_ascii=False,
            )
        return '{"tool": "step_failed", "params": {}, "reason": "unexpected"}'


def test_full_plan_tool_fail_repair_exhausted_then_step_planner(tmp_path: Path) -> None:
    gemma = _ToolFailRepairGemma()
    settings = SimpleNamespace(computer_use_full_plan_enabled=True)
    db = Database(path=tmp_path / "tf.db")
    assistant = IrisAssistant(db, ActionExecutor(db, {}), gemma, {}, settings=settings)  # type: ignore[arg-type]
    registry = assistant._executor.tool_registry
    call_count = {"n": 0}

    def _run_side_effect(name: str, ctx: object) -> AutomationToolResult:
        call_count["n"] += 1
        if name == "perceive_desktop":
            return _perceive_ok()
        if name == "launch_app":
            return AutomationToolResult(False, "launch failed", "tool_fail: launch_app")
        return AutomationToolResult(True, f"{name} ok", "detail")

    registry.run = MagicMock(side_effect=_run_side_effect)  # type: ignore[method-assign]

    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=20)  # type: ignore[arg-type]
    msg = agent.run("메모장 켜줘")

    assert gemma._repair_calls >= 1, "tool_fail 후 repair attempt 필요"
    step_planner = [
        c for c in gemma.calls if c and "Computer Use 플래너" in c[0].content
    ]
    assert step_planner, "repair exhausted 후 step planner 폴백"
    assert "폴백 완료" in msg or "완료" in msg
