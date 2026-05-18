"""assistant 패키지.

상위 패키지 import가 UI/자동화 전체를 끌어오지 않도록 lazy export를 사용한다.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "IrisAssistant",
    "AgentOrchestrator",
    "ActionPlan",
    "PlanStep",
    "ActionRequest",
    "SafetyResult",
    "evaluate",
    "quick_block_user_text",
    "LaunchStep",
    "LayoutStep",
    "TaskPlan",
    "plan_from_preset",
]


def __getattr__(name: str) -> Any:
    if name == "IrisAssistant":
        from iris.assistant.agent_adapter import IrisAssistant

        return IrisAssistant
    if name in {"ActionRequest", "SafetyResult", "evaluate", "quick_block_user_text"}:
        from iris.assistant import safety_guard

        return getattr(safety_guard, name)
    if name in {"LaunchStep", "LayoutStep", "TaskPlan", "plan_from_preset"}:
        from iris.assistant import task_planner

        return getattr(task_planner, name)
    if name == "AgentOrchestrator":
        from iris.assistant.orchestrator import AgentOrchestrator

        return AgentOrchestrator
    if name in {"ActionPlan", "PlanStep"}:
        from iris.assistant import action_plan

        return getattr(action_plan, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
