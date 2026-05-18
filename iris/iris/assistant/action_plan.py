"""LLM이 생성하는 JSON 실행 계획 모델 및 파싱."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

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

# 계획에 포함되면 즉시 거부되는 도구 (컴퓨터 직접 실행 금지)
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


def plan_to_json(plan: ActionPlan) -> str:
    """프롬프트 예시·로그용 직렬화."""
    payload = {
        "goal": plan.goal,
        "steps": [{"tool": s.tool, "args": s.args} for s in plan.steps],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
