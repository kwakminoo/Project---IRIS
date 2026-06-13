"""SafetyPolicy → 기존 SafetyGuard + AutomationToolRegistry Adapter."""

from __future__ import annotations

from typing import Any

from iris.assistant.safety_guard import ActionRequest, evaluate as safety_evaluate
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolContext
from iris.domain.execution.enums import PolicyDecisionKind
from iris.domain.execution.models import ActionProposal, PolicyDecision


class SafetyPolicyAdapter:
    """ActionProposal 정책 평가 — 기존 SafetyGuard·Registry 위임."""

    def __init__(
        self,
        registry: AutomationToolRegistry,
        *,
        default_tool_context: AutomationToolContext | None = None,
    ) -> None:
        self._registry = registry
        self._default_ctx = default_tool_context

    def evaluate(
        self,
        proposal: ActionProposal,
        *,
        tool_context: Any = None,
    ) -> PolicyDecision:
        ctx = tool_context or self._default_ctx
        # SafetyGuard 텍스트 기반 차단 (셸 명령 등)
        cmd_text = _proposal_to_command_text(proposal)
        if cmd_text:
            sg = safety_evaluate(ActionRequest(summary=cmd_text))
            if not sg.allowed:
                return PolicyDecision(
                    proposal_id=proposal.id,
                    decision=PolicyDecisionKind.DENY.value,
                    reason=sg.reason or "safety_guard_blocked",
                )

        if ctx is not None:
            ctx.params = dict(proposal.arguments)
            if self._registry.needs_approval(proposal.tool_name, ctx):
                return PolicyDecision(
                    proposal_id=proposal.id,
                    decision=PolicyDecisionKind.REQUIRE_APPROVAL.value,
                    reason="critical_risk_tool",
                )

        return PolicyDecision(
            proposal_id=proposal.id,
            decision=PolicyDecisionKind.ALLOW.value,
            reason="auto_allowed",
        )


def _proposal_to_command_text(proposal: ActionProposal) -> str:
    if proposal.tool_name == "run_shell":
        return str(proposal.arguments.get("command") or proposal.arguments.get("cmd") or "")
    return ""
