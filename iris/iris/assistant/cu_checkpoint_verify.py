"""Computer Use 체크포인트 검증 — 기계 게이트(perceive 필수) + LLM verify."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.ai.response_parser import extract_json_object
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.action_plan import ComputerUsePlanItem
from iris.assistant.cu_mechanical_verify import MechanicalVerifyResult, mechanical_verify_checkpoint
from iris.assistant.cu_perception import PerceptionObservation, has_valid_perception
from iris.assistant.cu_prompts import CU_CHECKPOINT_VERIFY_SYSTEM, cu_meta_system_prompt

if TYPE_CHECKING:
    from iris.ai.gemma_client import GemmaClient

_VALID_CHECKPOINT_IDS = frozenset(
    {
        "cp_app_open",
        "cp_focus",
        "cp_text_typed",
        "cp_message_sent",
        "cp_final",
    }
)
_VALID_FAILURE_KINDS = frozenset(
    {
        "missing_app",
        "wrong_focus",
        "text_missing",
        "text_partial",
        "ui_not_found",
        "user_input_needed",
        "unknown",
    }
)
_CHECKPOINT_OK_PREFIX = "checkpoint_ok:"
_CHECKPOINT_FAIL_PREFIX = "checkpoint_fail:"
_MAX_LLM_VERIFY_ATTEMPTS = 2


@dataclass(frozen=True)
class CheckpointVerifyResult:
    checkpoint_id: str
    achieved: bool
    failure_kind: str
    progress_summary: str
    gap: str
    last_ok_index: int
    resume_from_index: int
    confidence: float


def parse_checkpoint_verify_json(raw: str) -> CheckpointVerifyResult | None:
    """LLM 체크포인트 검증 JSON 파싱."""
    data = extract_json_object(raw)
    if not data:
        return None
    cp = str(data.get("checkpoint_id") or "").strip()
    if cp not in _VALID_CHECKPOINT_IDS:
        return None
    achieved = bool(data.get("achieved"))
    failure_kind = str(data.get("failure_kind") or "unknown").strip()
    if failure_kind not in _VALID_FAILURE_KINDS:
        failure_kind = "unknown"
    progress_summary = str(data.get("progress_summary") or "").strip()
    gap = str(data.get("gap") or "").strip()
    try:
        last_ok_index = int(data.get("last_ok_index", -1))
    except (TypeError, ValueError):
        last_ok_index = -1
    try:
        resume_from_index = int(data.get("resume_from_index", -1))
    except (TypeError, ValueError):
        resume_from_index = -1
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return CheckpointVerifyResult(
        checkpoint_id=cp,
        achieved=achieved,
        failure_kind=failure_kind,
        progress_summary=progress_summary,
        gap=gap,
        last_ok_index=last_ok_index,
        resume_from_index=resume_from_index,
        confidence=confidence,
    )


def has_recent_perceive(
    observations: Sequence[str],
    *,
    last_perception: PerceptionObservation | None = None,
    tail: int = 10,
) -> bool:
    """최근 perceive 존재 여부 — ctx.last_perception 기계 판정."""
    _ = observations, tail  # LLM verify 입력 추출용 observations와 구분
    return has_valid_perception(last_perception)


def has_recent_tool_fail(observations: Sequence[str], *, tail: int = 10) -> bool:
    for obs in reversed(observations[-tail:]):
        if obs.startswith("tool_fail:"):
            return True
    return False


def extract_windows_summary(observations: Sequence[str], *, tail: int = 12) -> str:
    for obs in reversed(observations[-tail:]):
        if obs.startswith("windows:"):
            return obs[len("windows:") :].strip()[:600]
    return ""


def extract_perceive_summary(observations: Sequence[str], *, tail: int = 12) -> str:
    parts: list[str] = []
    for obs in reversed(observations[-tail:]):
        s = obs.strip()
        if s.startswith("perceive:") or s.startswith("tool_ok:"):
            parts.append(s[:400])
        if len(parts) >= 4:
            break
    return "\n".join(reversed(parts))


def format_plans_executed(
    plans: Sequence[ComputerUsePlanItem],
    executed_through_index: int,
) -> str:
    """실행 완료된 plans[] 요약 — LLM verify 입력용."""
    lines: list[str] = []
    for item in plans:
        if item.index > executed_through_index:
            break
        cp = item.checkpoint_id or "null"
        reason = (item.reason or "")[:100]
        params = json.dumps(item.params, ensure_ascii=False)[:120]
        lines.append(
            f"[{item.index}] tool={item.tool} params={params} "
            f"checkpoint_id={cp} reason={reason}"
        )
    return "\n".join(lines)


def format_checkpoint_ok(result: CheckpointVerifyResult) -> str:
    """observation 마커 — 성공."""
    summary = result.progress_summary[:120]
    if summary:
        return f"{_CHECKPOINT_OK_PREFIX} {result.checkpoint_id} | {summary}"
    return f"{_CHECKPOINT_OK_PREFIX} {result.checkpoint_id}"


def format_checkpoint_fail(result: CheckpointVerifyResult) -> str:
    """observation 마커 — 실패 (Repair 입력용)."""
    gap = result.gap[:160]
    kind = result.failure_kind
    resume = result.resume_from_index
    payload = {
        "checkpoint_id": result.checkpoint_id,
        "failure_kind": kind,
        "gap": gap,
        "progress_summary": result.progress_summary[:120],
        "resume_from_index": resume,
    }
    return f"{_CHECKPOINT_FAIL_PREFIX} {json.dumps(payload, ensure_ascii=False)}"


def mechanical_prerequisites_met(
    observations: Sequence[str],
    *,
    last_perception: PerceptionObservation | None = None,
) -> tuple[bool, str]:
    """
    LLM 호출 전 기계 게이트 — perceive 필수, tool_fail 시 즉시 거부.
    반환: (통과 여부, 거부 사유 observation)
    """
    if has_recent_tool_fail(observations):
        return False, "checkpoint_verify_blocked: recent tool_fail"
    if not has_valid_perception(last_perception):
        return False, "checkpoint_verify_blocked: perceive required"
    return True, ""


def llm_verify_checkpoint(
    gemma: GemmaClient,
    *,
    goal: str,
    plan_id: str,
    checkpoint_id: str,
    executed_through_index: int,
    plans: Sequence[ComputerUsePlanItem],
    observations: Sequence[str],
    slots: dict[str, Any],
    screenshot_png: bytes | None = None,
) -> tuple[CheckpointVerifyResult | None, bool]:
    """LLM 체크포인트 검증 — (결과, vision_used)."""
    windows = extract_windows_summary(observations)
    perceive = extract_perceive_summary(observations)
    plans_text = format_plans_executed(plans, executed_through_index)
    slots_line = json.dumps(slots, ensure_ascii=False)[:400] if slots else "{}"
    shot_tag = "screenshot_attached=yes" if screenshot_png else "screenshot_attached=no"
    vision_line = "첨부 화면이 현재 PC 상태입니다.\n" if screenshot_png else ""
    user_body = (
        f"goal: {goal}\n"
        f"plan_id: {plan_id}\n"
        f"checkpoint_id: {checkpoint_id}\n"
        f"executed_through_index: {executed_through_index}\n"
        f"slots: {slots_line}\n"
        f"{shot_tag}\n"
        f"windows:\n{windows or '(없음)'}\n"
        f"perceive_summary:\n{perceive or '(없음)'}\n"
        f"plans_executed:\n{plans_text or '(없음)'}\n\n"
        f"{vision_line}"
        "JSON만 출력하세요."
    )
    images: tuple[bytes, ...] = (screenshot_png,) if screenshot_png else ()
    msgs = [
        ChatMessage("system", cu_meta_system_prompt(CU_CHECKPOINT_VERIFY_SYSTEM)),
        ChatMessage("user", user_body, images=images),
    ]
    vision_used = False
    if images and hasattr(gemma, "chat_with_images"):
        raw, vision_used = gemma.chat_with_images(
            msgs,
            purpose=LlmPurpose.COMPUTER_USE,
            lane="computer_use",
        )
    else:
        raw = gemma.chat(
            msgs,
            purpose=LlmPurpose.COMPUTER_USE,
            lane="computer_use",
        )
    if _is_llm_unavailable(raw):
        return None, vision_used
    parsed = parse_checkpoint_verify_json(raw)
    if parsed and parsed.checkpoint_id != checkpoint_id:
        # LLM이 다른 checkpoint_id를 반환하면 요청 id로 정규화
        parsed = CheckpointVerifyResult(
            checkpoint_id=checkpoint_id,
            achieved=parsed.achieved,
            failure_kind=parsed.failure_kind,
            progress_summary=parsed.progress_summary,
            gap=parsed.gap,
            last_ok_index=parsed.last_ok_index,
            resume_from_index=parsed.resume_from_index,
            confidence=parsed.confidence,
        )
    return parsed, vision_used


def mechanical_to_checkpoint_result(
    mech: MechanicalVerifyResult,
    *,
    executed_through_index: int,
) -> CheckpointVerifyResult:
    """기계 검증 결과 → CheckpointVerifyResult 변환."""
    achieved = mech.status == "success"
    if achieved:
        last_ok = executed_through_index
        resume = executed_through_index + 1
    else:
        last_ok = max(-1, executed_through_index - 1)
        resume = executed_through_index
    failure_kind = mech.failure_kind if mech.status == "failed" else "unknown"
    return CheckpointVerifyResult(
        checkpoint_id=mech.checkpoint_id,
        achieved=achieved,
        failure_kind=failure_kind,
        progress_summary=mech.progress_summary,
        gap=mech.gap,
        last_ok_index=last_ok,
        resume_from_index=resume,
        confidence=mech.confidence,
    )


def verify_checkpoint_with_llm_retries(
    gemma: GemmaClient,
    *,
    goal: str,
    plan_id: str,
    checkpoint_id: str,
    executed_through_index: int,
    plans: Sequence[ComputerUsePlanItem],
    observations: Sequence[str],
    slots: dict[str, Any],
    screenshot_png: bytes | None = None,
    max_attempts: int = _MAX_LLM_VERIFY_ATTEMPTS,
) -> tuple[CheckpointVerifyResult | None, bool]:
    """LLM verify 최대 max_attempts회."""
    last: CheckpointVerifyResult | None = None
    vision_used = False
    for _ in range(max(1, max_attempts)):
        result, used = llm_verify_checkpoint(
            gemma,
            goal=goal,
            plan_id=plan_id,
            checkpoint_id=checkpoint_id,
            executed_through_index=executed_through_index,
            plans=plans,
            observations=observations,
            slots=slots,
            screenshot_png=screenshot_png,
        )
        vision_used = vision_used or used
        if result is None:
            return None, vision_used
        last = result
        if result.achieved:
            return result, vision_used
    return last, vision_used


def verify_checkpoint_hybrid(
    gemma: GemmaClient,
    *,
    goal: str,
    plan_id: str,
    checkpoint_id: str,
    executed_through_index: int,
    plans: Sequence[ComputerUsePlanItem],
    observations: Sequence[str],
    slots: dict[str, Any],
    cu_ctx: Any,
    last_perception: PerceptionObservation | None = None,
    screenshot_png: bytes | None = None,
    max_attempts: int = _MAX_LLM_VERIFY_ATTEMPTS,
) -> tuple[CheckpointVerifyResult | None, bool]:
    """
    기계 검증 우선 — status != inconclusive 이면 LLM 생략.
    inconclusive만 verify_checkpoint_with_llm_retries 호출.
    """
    mech = mechanical_verify_checkpoint(
        checkpoint_id,
        perception=last_perception,
        slots=slots,
        executed_plans=plans,
        cu_ctx=cu_ctx,
        executed_through_index=executed_through_index,
    )
    if mech.status != "inconclusive":
        return mechanical_to_checkpoint_result(mech, executed_through_index=executed_through_index), False
    return verify_checkpoint_with_llm_retries(
        gemma,
        goal=goal,
        plan_id=plan_id,
        checkpoint_id=checkpoint_id,
        executed_through_index=executed_through_index,
        plans=plans,
        observations=observations,
        slots=slots,
        screenshot_png=screenshot_png,
        max_attempts=max_attempts,
    )


def _is_llm_unavailable(text: str) -> bool:
    t = text.strip()
    return t == FALLBACK_KO or "로컬 언어 모델에 연결할 수 없습니다" in t
