"""정책 평가 Port — Infrastructure Adapter가 구현."""

from __future__ import annotations

from typing import Any, Protocol

from iris.domain.execution.models import ActionProposal, PolicyDecision


class SafetyPolicyPort(Protocol):
    """ActionProposal 정책 평가."""

    def evaluate(self, proposal: ActionProposal, *, tool_context: Any = None) -> PolicyDecision: ...


class AutomationToolPort(Protocol):
    """자동화 도구 실행."""

    def needs_approval(self, tool_name: str, params: dict[str, Any]) -> bool: ...
    def preview(self, tool_name: str, params: dict[str, Any]) -> str: ...
    def run(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        approved: bool,
        summary: str = "",
    ) -> Any: ...
