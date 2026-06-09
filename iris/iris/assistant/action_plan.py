"""LLM이 생성하는 JSON 실행 계획 모델 및 파싱."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from iris.assistant.tool_param_normalize import normalize_computer_use_params

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")

# 오케스트레이터가 허용하는 도구 이름
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "safety_check",
        "intent_route",
        "assistant_dispatch",
        "monitoring_status",
        "gemma_finalize",
    }
)

# 전체 플랜 plans[].tool 허용 (run_shell·종료 도구 제외)
FULL_PLAN_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "get_system_info",
        "launch_app",
        "focus_window",
        "open_url",
        "search_web",
        "type_text",
        "click",
        "list_open_windows",
        "uia_snapshot",
        "perceive_desktop",
        "uia_click",
        "send_hotkey",
        "call_integration",
        "ask_user",
    }
)

FULL_PLAN_BLOCKED_TOOLS: frozenset[str] = frozenset(
    {"run_shell", "step_complete", "step_failed"}
)

# Computer Use 에이전트 한 스텝 JSON 허용 도구
ALLOWED_COMPUTER_USE_TOOLS: frozenset[str] = frozenset(
    {
        "get_system_info",
        "launch_app",
        "focus_window",
        "open_url",
        "search_web",
        "type_text",
        "click",
        "run_shell",
        "read_screen_summary",
        "list_open_windows",
        "uia_snapshot",
        "perceive_desktop",
        "uia_click",
        "send_hotkey",
        "call_integration",
        "step_complete",
        "step_failed",
        "ask_user",
    }
)

# 계획에 포함되면 즉시 거부되는 도구 (오케스트레이터 레거시 이름)
BLOCKED_TOOLS: frozenset[str] = frozenset(
    {
        "app_launch",
        "window_control",
        "keyboard_input",
        "mouse_click",
        "shell_run",
        "file_delete",
    }
)


@dataclass(frozen=True)
class PlanStep:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComputerUseStep:
    """Computer Use 루프 한 스텝 — LLM이 tool/params/reason JSON으로 출력."""

    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True)
class ComputerUsePlanItem:
    """전체 플랜 plans[] 한 항목."""

    index: int
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    checkpoint_id: str | None = None


@dataclass(frozen=True)
class ComputerUseFullPlan:
    """초기 Perceive 이후 1회 작성되는 전체 실행 플랜."""

    goal: str
    plan_id: str
    plans: tuple[ComputerUsePlanItem, ...]
    expected_checkpoints: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class ComputerUseRepairPlan:
    """체크포인트 실패 시 gap 보완용 국소 repair_steps[] (1~5)."""

    plan_id: str
    repair_attempt: int
    gap: str
    repair_steps: tuple[ComputerUsePlanItem, ...]
    recommend_fail: bool = False
    ask_user: str | None = None


@dataclass
class ActionPlan:
    """사용자 요청을 순차 실행할 JSON 계획."""

    goal: str
    steps: list[PlanStep]


def default_plan(user_text: str) -> ActionPlan:
    """LLM 파싱 실패 시 사용하는 안전한 기본 계획."""
    return ActionPlan(
        goal=user_text.strip()[:200] or "사용자 요청 처리",
        steps=[
            PlanStep("safety_check"),
            PlanStep("intent_route"),
            PlanStep("assistant_dispatch"),
            PlanStep("gemma_finalize", {"only_if_no_direct_reply": True}),
        ],
    )


def _normalize_step(raw: Any) -> PlanStep | None:
    if not isinstance(raw, dict):
        return None
    tool = raw.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return None
    name = tool.strip()
    if name in BLOCKED_TOOLS:
        return None
    if name not in ALLOWED_TOOLS:
        return None
    args = raw.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    return PlanStep(name, dict(args))


def parse_action_plan(text: str) -> ActionPlan | None:
    """LLM 응답 또는 JSON 문자열에서 ActionPlan 추출."""
    blob = text.strip()
    m = _JSON_BLOCK.search(blob)
    if m:
        blob = m.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    goal = data.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        goal = "사용자 요청 처리"

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    steps: list[PlanStep] = []
    for item in raw_steps:
        step = _normalize_step(item)
        if step is None:
            return None
        steps.append(step)

    if not steps:
        return None
    # 마지막 단계는 반드시 요약 도구로 종료 (직접 답변 방지)
    if steps[-1].tool != "gemma_finalize":
        steps.append(PlanStep("gemma_finalize", {"only_if_no_direct_reply": True}))

    return ActionPlan(goal=goal.strip(), steps=steps)


def parse_computer_use_step(text: str) -> ComputerUseStep | None:
    """LLM 응답에서 Computer Use 단일 스텝 JSON 추출."""
    blob = text.strip()
    m = _JSON_BLOCK.search(blob)
    if m:
        blob = m.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    tool = data.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return None
    name = tool.strip()
    if name not in ALLOWED_COMPUTER_USE_TOOLS:
        return None
    params = data.get("params") or data.get("args") or {}
    if not isinstance(params, dict):
        params = {}
    reason = data.get("reason")
    if not isinstance(reason, str):
        reason = ""
    normalized = normalize_computer_use_params(name, dict(params))
    return ComputerUseStep(name, normalized, reason.strip())


def _normalize_full_plan_item(raw: Any, fallback_index: int) -> ComputerUsePlanItem | None:
    if not isinstance(raw, dict):
        return None
    tool = raw.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return None
    name = tool.strip()
    if name in FULL_PLAN_BLOCKED_TOOLS or name not in FULL_PLAN_ALLOWED_TOOLS:
        return None
    params = raw.get("params") or raw.get("args") or {}
    if not isinstance(params, dict):
        params = {}
    reason = raw.get("reason")
    if not isinstance(reason, str):
        reason = ""
    idx_raw = raw.get("index", fallback_index)
    try:
        idx = int(idx_raw)
    except (TypeError, ValueError):
        idx = fallback_index
    cp = raw.get("checkpoint_id")
    checkpoint_id: str | None
    if cp is None or (isinstance(cp, str) and not cp.strip()):
        checkpoint_id = None
    elif isinstance(cp, str):
        checkpoint_id = cp.strip()
    else:
        checkpoint_id = None
    normalized = normalize_computer_use_params(name, dict(params))
    return ComputerUsePlanItem(
        index=idx,
        tool=name,
        params=normalized,
        reason=reason.strip(),
        checkpoint_id=checkpoint_id,
    )


def parse_computer_use_full_plan(text: str) -> ComputerUseFullPlan | None:
    """LLM 응답에서 Computer Use 전체 플랜 JSON 추출."""
    blob = text.strip()
    m = _JSON_BLOCK.search(blob)
    if m:
        blob = m.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    goal = data.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return None

    plan_id = data.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        plan_id = "plan-unknown"

    raw_plans = data.get("plans")
    if not isinstance(raw_plans, list) or not raw_plans:
        return None

    items: list[ComputerUsePlanItem] = []
    for i, raw in enumerate(raw_plans):
        item = _normalize_full_plan_item(raw, i)
        if item is None:
            return None
        items.append(item)

    # ask_user 단독 1스텝 예외, 그 외 2~12스텝 (checkpoint_id 없는 짧은 플랜 허용)
    if len(items) == 1 and items[0].tool == "ask_user":
        pass
    elif len(items) < 2 or len(items) > 12:
        return None

    expected: tuple[str, ...] = ()
    raw_cp = data.get("expected_checkpoints")
    if isinstance(raw_cp, list):
        expected = tuple(
            str(x).strip() for x in raw_cp if isinstance(x, str) and str(x).strip()
        )

    confidence = data.get("confidence", 0.0)
    try:
        conf_f = float(confidence)
    except (TypeError, ValueError):
        conf_f = 0.0

    return ComputerUseFullPlan(
        goal=goal.strip(),
        plan_id=plan_id.strip(),
        plans=tuple(items),
        expected_checkpoints=expected,
        confidence=conf_f,
    )


def _normalize_repair_step(raw: Any, fallback_index: int) -> ComputerUsePlanItem | None:
    """repair_steps[] 항목 — ask_user·run_shell 금지."""
    if not isinstance(raw, dict):
        return None
    tool = raw.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return None
    name = tool.strip()
    if name in FULL_PLAN_BLOCKED_TOOLS or name not in FULL_PLAN_ALLOWED_TOOLS:
        return None
    if name == "ask_user":
        return None
    params = raw.get("params") or raw.get("args") or {}
    if not isinstance(params, dict):
        params = {}
    reason = raw.get("reason")
    if not isinstance(reason, str):
        reason = ""
    cp = raw.get("checkpoint_id")
    checkpoint_id: str | None
    if cp is None or (isinstance(cp, str) and not cp.strip()):
        checkpoint_id = None
    elif isinstance(cp, str):
        checkpoint_id = cp.strip()
    else:
        checkpoint_id = None
    normalized = normalize_computer_use_params(name, dict(params))
    return ComputerUsePlanItem(
        index=fallback_index,
        tool=name,
        params=normalized,
        reason=reason.strip(),
        checkpoint_id=checkpoint_id,
    )


def parse_computer_use_repair_plan(
    text: str,
    *,
    expected_plan_id: str = "",
) -> ComputerUseRepairPlan | None:
    """LLM Repair 계획 JSON 파싱 — repair_steps 0~5개."""
    blob = text.strip()
    m = _JSON_BLOCK.search(blob)
    if m:
        blob = m.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    plan_id = str(data.get("plan_id") or "").strip()
    if not plan_id:
        return None
    if expected_plan_id and plan_id != expected_plan_id:
        return None

    try:
        repair_attempt = int(data.get("repair_attempt", 1))
    except (TypeError, ValueError):
        repair_attempt = 1
    repair_attempt = max(1, min(3, repair_attempt))

    gap = str(data.get("gap") or "").strip()
    recommend_fail = bool(data.get("recommend_fail"))

    ask_raw = data.get("ask_user")
    ask_user: str | None
    if ask_raw is None:
        ask_user = None
    elif isinstance(ask_raw, str) and ask_raw.strip():
        ask_user = ask_raw.strip()
    elif isinstance(ask_raw, dict):
        q = ask_raw.get("question") or ask_raw.get("text")
        ask_user = str(q).strip() if q else None
    else:
        ask_user = None

    raw_steps = data.get("repair_steps")
    if raw_steps is None:
        raw_steps = []
    if not isinstance(raw_steps, list):
        return None
    if len(raw_steps) > 5:
        return None

    steps: list[ComputerUsePlanItem] = []
    for i, raw in enumerate(raw_steps):
        item = _normalize_repair_step(raw, i)
        if item is None:
            return None
        steps.append(item)

    if ask_user and steps:
        return None

    return ComputerUseRepairPlan(
        plan_id=plan_id,
        repair_attempt=repair_attempt,
        gap=gap,
        repair_steps=tuple(steps),
        recommend_fail=recommend_fail,
        ask_user=ask_user,
    )


def plan_to_json(plan: ActionPlan) -> str:
    """프롬프트 예시·로그용 직렬화."""
    payload = {
        "goal": plan.goal,
        "steps": [{"tool": s.tool, "args": s.args} for s in plan.steps],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def full_plan_to_dict(plan: ComputerUseFullPlan) -> dict[str, Any]:
    """PendingComputerUseGoal·task_session용 full_plan 스냅샷."""
    return {
        "goal": plan.goal,
        "plan_id": plan.plan_id,
        "plans": [
            {
                "index": item.index,
                "tool": item.tool,
                "params": dict(item.params),
                "reason": item.reason,
                "checkpoint_id": item.checkpoint_id,
            }
            for item in plan.plans
        ],
        "expected_checkpoints": list(plan.expected_checkpoints),
        "confidence": plan.confidence,
    }


def full_plan_from_dict(data: dict[str, Any]) -> ComputerUseFullPlan | None:
    """스냅샷 dict → ComputerUseFullPlan (parse_computer_use_full_plan 재사용)."""
    if not data:
        return None
    try:
        blob = json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    return parse_computer_use_full_plan(blob)
