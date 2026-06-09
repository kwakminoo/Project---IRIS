"""Computer Use Repair 계획기(CU_REPAIR_PLANNER) 파싱·LLM 테스트."""

from __future__ import annotations

import json
from typing import Sequence

from iris.ai.gemma_client import ChatMessage
from iris.assistant.action_plan import (
    ComputerUsePlanItem,
    parse_computer_use_repair_plan,
)
from iris.assistant.cu_checkpoint_verify import CheckpointVerifyResult
from iris.assistant.cu_prompts import (
    CU_META_PIPELINE_POLICY,
    CU_REPAIR_PLANNER_SYSTEM,
    cu_meta_system_prompt,
)
from iris.assistant.cu_repair_planner import (
    format_original_plans,
    format_verify_result,
    llm_repair_plan,
)


def _sample_repair_json(**overrides: object) -> str:
    base = {
        "plan_id": "test-plan-1",
        "repair_attempt": 1,
        "gap": "focus_window 후 type_text 미실행",
        "repair_steps": [
            {
                "tool": "focus_window",
                "params": {"title_sub": "메모장"},
                "reason": "메모장 포커스",
            },
            {
                "tool": "type_text",
                "params": {"text": "hello"},
                "reason": "텍스트 입력",
                "checkpoint_id": "cp_text_typed",
            },
        ],
        "recommend_fail": False,
        "ask_user": None,
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


def test_parse_computer_use_repair_plan_valid() -> None:
    plan = parse_computer_use_repair_plan(
        _sample_repair_json(), expected_plan_id="test-plan-1"
    )
    assert plan is not None
    assert plan.plan_id == "test-plan-1"
    assert len(plan.repair_steps) == 2
    assert plan.repair_steps[1].checkpoint_id == "cp_text_typed"


def test_parse_computer_use_repair_plan_rejects_run_shell() -> None:
    data = json.loads(_sample_repair_json())
    data["repair_steps"][0]["tool"] = "run_shell"
    assert parse_computer_use_repair_plan(json.dumps(data)) is None


def test_parse_computer_use_repair_plan_rejects_plan_id_mismatch() -> None:
    assert (
        parse_computer_use_repair_plan(
            _sample_repair_json(), expected_plan_id="other-id"
        )
        is None
    )


def test_parse_computer_use_repair_plan_ask_user_only() -> None:
    plan = parse_computer_use_repair_plan(
        _sample_repair_json(
            repair_steps=[],
            ask_user="어떤 대화방에 보낼까요?",
        )
    )
    assert plan is not None
    assert plan.ask_user == "어떤 대화방에 보낼까요?"
    assert not plan.repair_steps


def test_parse_computer_use_repair_plan_rejects_too_many_steps() -> None:
    steps = [
        {"tool": "focus_window", "params": {"title_sub": "x"}, "reason": "r"}
        for _ in range(6)
    ]
    assert parse_computer_use_repair_plan(_sample_repair_json(repair_steps=steps)) is None


def test_format_original_plans_and_verify_result() -> None:
    plans = (
        ComputerUsePlanItem(0, "list_open_windows", {}, "창"),
        ComputerUsePlanItem(1, "launch_app", {"app_key": "notepad"}, "실행", "cp_app_open"),
    )
    text = format_original_plans(plans)
    assert "[0]" in text
    assert "[1]" in text

    verify = CheckpointVerifyResult(
        checkpoint_id="cp_text_typed",
        achieved=False,
        failure_kind="text_missing",
        progress_summary="본문 비어 있음",
        gap="type_text 필요",
        last_ok_index=2,
        resume_from_index=3,
        confidence=0.8,
    )
    assert "text_missing" in format_verify_result(verify)


class _RepairGemma:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        return self._response


def test_llm_repair_plan_uses_system_prompt() -> None:
    gemma = _RepairGemma(_sample_repair_json())
    verify = CheckpointVerifyResult(
        checkpoint_id="cp_text_typed",
        achieved=False,
        failure_kind="text_missing",
        progress_summary="본문 비어 있음",
        gap="type_text 필요",
        last_ok_index=2,
        resume_from_index=3,
        confidence=0.8,
    )
    plans = (ComputerUsePlanItem(2, "focus_window", {"title_sub": "메모장"}, "포커스"),)
    obs = ["windows: 메모장", "perceive: ocr | Notepad"]
    result = llm_repair_plan(
        gemma,  # type: ignore[arg-type]
        goal="메모장에 hello",
        plan_id="test-plan-1",
        original_plans=plans,
        verify_result=verify,
        observations=obs,
        slots={"text_to_type": "hello"},
        repair_attempt=1,
    )
    assert result is not None
    assert len(result.repair_steps) == 2
    assert gemma.calls
    assert "Repair 계획기" in gemma.calls[0][0].content
    assert CU_META_PIPELINE_POLICY in gemma.calls[0][0].content


def test_cu_repair_planner_system_contains_rules() -> None:
    assert "repair_steps" in CU_REPAIR_PLANNER_SYSTEM
    assert "recommend_fail" in CU_REPAIR_PLANNER_SYSTEM
    assert "전체 플랜을 다시 짜지 마세요" in CU_REPAIR_PLANNER_SYSTEM
    assert "run_shell 추가 금지" in CU_REPAIR_PLANNER_SYSTEM


def test_cu_meta_pipeline_policy_contains_runtime_steps() -> None:
    assert "Repair Planner" in CU_META_PIPELINE_POLICY
    assert "repair_attempt > 3" in CU_META_PIPELINE_POLICY
    assert "run_shell" in CU_META_PIPELINE_POLICY


def test_cu_meta_system_prompt_composes_base_and_policy() -> None:
    composed = cu_meta_system_prompt(CU_REPAIR_PLANNER_SYSTEM, extra="extra block")
    assert CU_REPAIR_PLANNER_SYSTEM in composed
    assert CU_META_PIPELINE_POLICY in composed
    assert "extra block" in composed
