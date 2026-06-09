"""Computer Use 체크포인트 검증(CU_CHECKPOINT_VERIFY) 파싱·게이트·LLM 테스트."""

from __future__ import annotations

import json
from typing import Sequence

from iris.ai.gemma_client import ChatMessage
from iris.assistant.action_plan import ComputerUsePlanItem
from iris.assistant.cu_checkpoint_verify import (
    CheckpointVerifyResult,
    extract_perceive_summary,
    extract_windows_summary,
    format_checkpoint_fail,
    format_checkpoint_ok,
    format_plans_executed,
    has_recent_perceive,
    llm_verify_checkpoint,
    mechanical_prerequisites_met,
    mechanical_to_checkpoint_result,
    parse_checkpoint_verify_json,
    verify_checkpoint_hybrid,
)
from iris.assistant.cu_mechanical_verify import MechanicalVerifyResult
from iris.assistant.cu_perception import PerceptionObservation
from iris.assistant.cu_prompts import CU_CHECKPOINT_VERIFY_SYSTEM


def _sample_verify_json(**overrides: object) -> str:
    base = {
        "checkpoint_id": "cp_text_typed",
        "achieved": False,
        "failure_kind": "text_missing",
        "progress_summary": "메모장은 열려 있으나 본문이 비어 있음",
        "gap": "type_text 미실행",
        "last_ok_index": 2,
        "resume_from_index": 3,
        "confidence": 0.85,
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


def test_parse_checkpoint_verify_json_valid() -> None:
    result = parse_checkpoint_verify_json(_sample_verify_json())
    assert result is not None
    assert result.checkpoint_id == "cp_text_typed"
    assert result.achieved is False
    assert result.failure_kind == "text_missing"
    assert result.resume_from_index == 3


def test_parse_checkpoint_verify_json_rejects_invalid_checkpoint() -> None:
    assert parse_checkpoint_verify_json(_sample_verify_json(checkpoint_id="cp_unknown")) is None


def test_mechanical_prerequisites_require_perceive() -> None:
    obs = ["tool_ok: launch_app ok"]
    ok, msg = mechanical_prerequisites_met(obs, last_perception=None)
    assert ok is False
    assert "perceive" in msg


def test_mechanical_prerequisites_block_tool_fail() -> None:
    from iris.assistant.cu_perception import PerceptionObservation

    obs = ["windows: Notepad", "perceive: ocr | hello", "tool_fail: type_text"]
    ok, msg = mechanical_prerequisites_met(
        obs,
        last_perception=PerceptionObservation(
            perception_source="ocr",
            captured_at=1.0,
        ),
    )
    assert ok is False
    assert "tool_fail" in msg


def test_has_recent_perceive_uses_structured_perception() -> None:
    from iris.assistant.cu_perception import PerceptionObservation

    valid = PerceptionObservation(perception_source="ocr", captured_at=1.0)
    assert has_recent_perceive([], last_perception=valid)
    assert not has_recent_perceive([], last_perception=None)


def test_extract_summaries_from_observations() -> None:
    obs = [
        "windows: [{\"title\":\"메모장\"}]",
        "perceive: ocr | Notepad | hello",
    ]
    assert "메모장" in extract_windows_summary(obs)
    assert "hello" in extract_perceive_summary(obs)


def test_format_plans_executed_truncates_future_steps() -> None:
    plans = (
        ComputerUsePlanItem(0, "list_open_windows", {}, "창 확인"),
        ComputerUsePlanItem(1, "launch_app", {"app_key": "notepad"}, "실행", "cp_app_open"),
        ComputerUsePlanItem(2, "focus_window", {"title_sub": "메모장"}, "포커스"),
    )
    text = format_plans_executed(plans, executed_through_index=1)
    assert "[1]" in text
    assert "[2]" not in text


def test_format_checkpoint_markers() -> None:
    result = CheckpointVerifyResult(
        checkpoint_id="cp_app_open",
        achieved=True,
        failure_kind="unknown",
        progress_summary="메모장 열림",
        gap="",
        last_ok_index=1,
        resume_from_index=2,
        confidence=0.9,
    )
    assert "checkpoint_ok:" in format_checkpoint_ok(result)
    fail = CheckpointVerifyResult(
        checkpoint_id="cp_focus",
        achieved=False,
        failure_kind="wrong_focus",
        progress_summary="포커스 불일치",
        gap="focus_window 재실행 필요",
        last_ok_index=1,
        resume_from_index=2,
        confidence=0.7,
    )
    fail_line = format_checkpoint_fail(fail)
    assert fail_line.startswith("checkpoint_fail:")
    assert "wrong_focus" in fail_line


class _CheckpointGemma:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        return self._response


def test_llm_verify_checkpoint_uses_system_prompt() -> None:
    gemma = _CheckpointGemma(_sample_verify_json(achieved=True))
    plans = (ComputerUsePlanItem(1, "launch_app", {"app_key": "notepad"}, "실행", "cp_app_open"),)
    obs = ["windows: 메모장", "perceive: ocr | Notepad"]
    result, vision_used = llm_verify_checkpoint(
        gemma,  # type: ignore[arg-type]
        goal="메모장 열기",
        plan_id="p1",
        checkpoint_id="cp_app_open",
        executed_through_index=1,
        plans=plans,
        observations=obs,
        slots={"app_key": "notepad"},
    )
    assert result is not None
    assert result.achieved is True
    assert vision_used is False
    assert gemma.calls
    assert "체크포인트 검증기" in gemma.calls[0][0].content


def test_cu_checkpoint_verify_system_contains_rules() -> None:
    assert "cp_app_open" in CU_CHECKPOINT_VERIFY_SYSTEM
    assert "cp_final" in CU_CHECKPOINT_VERIFY_SYSTEM
    assert "failure_kind" in CU_CHECKPOINT_VERIFY_SYSTEM
    assert "perceive 없이 achieved=true 금지" in CU_CHECKPOINT_VERIFY_SYSTEM


def test_mechanical_to_checkpoint_result_success() -> None:
    mech = MechanicalVerifyResult(
        checkpoint_id="cp_text_typed",
        status="success",
        failure_kind="unknown",
        gap="",
        progress_summary="입력 확인",
        confidence=1.0,
    )
    cp = mechanical_to_checkpoint_result(mech, executed_through_index=3)
    assert cp.achieved is True
    assert cp.last_ok_index == 3
    assert cp.confidence == 1.0


class _HybridGemma:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls += 1
        return _sample_verify_json(achieved=True)


def test_verify_checkpoint_hybrid_skips_llm_on_mechanical_success() -> None:
    """last_type_verify=True면 LLM 호출 없이 cp_text_typed success."""
    from types import SimpleNamespace

    gemma = _HybridGemma()
    plans = (
        ComputerUsePlanItem(3, "type_text", {"text": "hello"}, "입력", "cp_text_typed"),
    )
    cu_ctx = SimpleNamespace(last_type_verify=True, last_focus_hwnd=0, observations=[])
    perception = PerceptionObservation(
        active_window_title="무제 - 메모장",
        perception_source="ocr",
        captured_at=1.0,
    )
    result, vision_used = verify_checkpoint_hybrid(
        gemma,  # type: ignore[arg-type]
        goal="메모장에 hello 입력",
        plan_id="p1",
        checkpoint_id="cp_text_typed",
        executed_through_index=3,
        plans=plans,
        observations=["perceive: ocr | 메모장"],
        slots={"app_key": "notepad", "text": "hello"},
        cu_ctx=cu_ctx,
        last_perception=perception,
    )
    assert result is not None
    assert result.achieved is True
    assert result.confidence == 1.0
    assert gemma.calls == 0
    assert vision_used is False


def test_verify_checkpoint_hybrid_calls_llm_on_inconclusive() -> None:
    gemma = _HybridGemma()
    from types import SimpleNamespace

    cu_ctx = SimpleNamespace(last_type_verify=None, last_focus_hwnd=0, observations=[])
    result, _ = verify_checkpoint_hybrid(
        gemma,  # type: ignore[arg-type]
        goal="메모장 열기",
        plan_id="p1",
        checkpoint_id="cp_app_open",
        executed_through_index=1,
        plans=(),
        observations=[],
        slots={},
        cu_ctx=cu_ctx,
        last_perception=None,
    )
    assert result is not None
    assert gemma.calls >= 1
