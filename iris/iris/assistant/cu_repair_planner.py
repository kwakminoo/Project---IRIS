"""Computer Use Repair 계획기 — gap 기준 국소 repair_steps[] (전체 replan 금지)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Sequence

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.action_plan import (
    ComputerUsePlanItem,
    ComputerUseRepairPlan,
    parse_computer_use_repair_plan,
)
from iris.assistant.cu_checkpoint_verify import (
    CheckpointVerifyResult,
    extract_perceive_summary,
    extract_windows_summary,
    format_plans_executed,
)
from iris.assistant.cu_prompts import CU_REPAIR_PLANNER_SYSTEM, cu_meta_system_prompt
from iris.assistant.execution_tier_policy import EXECUTION_TIER_PLANNER_BLOCK

if TYPE_CHECKING:
    from iris.ai.gemma_client import GemmaClient


def format_original_plans(plans: Sequence[ComputerUsePlanItem]) -> str:
    """원본 plans[] 전체 — Repair 입력용 (변경 금지 참조)."""
    lines: list[str] = []
    for item in plans:
        cp = item.checkpoint_id or "null"
        params = json.dumps(item.params, ensure_ascii=False)[:120]
        lines.append(
            f"[{item.index}] tool={item.tool} params={params} "
            f"checkpoint_id={cp} reason={(item.reason or '')[:80]}"
        )
    return "\n".join(lines)


def format_verify_result(result: CheckpointVerifyResult) -> str:
    """CheckpointVerifyResult — Repair LLM 입력용."""
    payload = {
        "checkpoint_id": result.checkpoint_id,
        "achieved": result.achieved,
        "failure_kind": result.failure_kind,
        "gap": result.gap[:200],
        "progress_summary": result.progress_summary[:160],
        "last_ok_index": result.last_ok_index,
        "resume_from_index": result.resume_from_index,
        "confidence": result.confidence,
    }
    return json.dumps(payload, ensure_ascii=False)


def llm_repair_plan(
    gemma: GemmaClient,
    *,
    goal: str,
    plan_id: str,
    original_plans: Sequence[ComputerUsePlanItem],
    verify_result: CheckpointVerifyResult,
    observations: Sequence[str],
    slots: dict[str, Any],
    repair_attempt: int,
    screenshot_png: bytes | None = None,
) -> ComputerUseRepairPlan | None:
    """Repair Planner LLM 호출 — (파싱된 repair plan | None)."""
    windows = extract_windows_summary(observations)
    perceive = extract_perceive_summary(observations)
    plans_text = format_original_plans(original_plans)
    verify_line = format_verify_result(verify_result)
    slots_line = json.dumps(slots, ensure_ascii=False)[:400] if slots else "{}"
    shot_tag = "screenshot_attached=yes" if screenshot_png else "screenshot_attached=no"
    vision_line = "첨부 화면이 현재 PC 상태입니다.\n" if screenshot_png else ""
    attempt = max(1, min(3, repair_attempt))

    user_body = (
        f"goal: {goal}\n"
        f"plan_id: {plan_id}\n"
        f"repair_attempt: {attempt}\n"
        f"slots: {slots_line}\n"
        f"{shot_tag}\n"
        f"verify_result: {verify_line}\n"
        f"windows:\n{windows or '(없음)'}\n"
        f"perceive_summary:\n{perceive or '(없음)'}\n"
        f"original_plans[] (변경 금지, 참조만):\n{plans_text or '(없음)'}\n\n"
        f"{vision_line}"
        "repair_steps[] JSON만 출력하세요."
    )
    allowed_extra = (
        f"{EXECUTION_TIER_PLANNER_BLOCK}\n\n"
        "repair_steps[].tool 허용: get_system_info, launch_app, focus_window, open_url, "
        "search_web, list_open_windows, perceive_desktop, uia_snapshot, uia_click, "
        "send_hotkey, type_text, click, call_integration (run_shell·ask_user in steps 금지)"
    )
    system = cu_meta_system_prompt(CU_REPAIR_PLANNER_SYSTEM, extra=allowed_extra)
    images: tuple[bytes, ...] = (screenshot_png,) if screenshot_png else ()
    msgs = [
        ChatMessage("system", system),
        ChatMessage("user", user_body, images=images),
    ]
    if images and hasattr(gemma, "chat_with_images"):
        raw, _used = gemma.chat_with_images(
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
        return None
    return parse_computer_use_repair_plan(raw, expected_plan_id=plan_id)


def _is_llm_unavailable(text: str) -> bool:
    t = text.strip()
    return t == FALLBACK_KO or "로컬 언어 모델에 연결할 수 없습니다" in t
