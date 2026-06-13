"""AutomationToolRegistry → AutomationToolPort Adapter."""

from __future__ import annotations

from typing import Any

from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolContext, AutomationToolResult


class ToolRegistryAdapter:
    """기존 AutomationToolRegistry 래핑."""

    def __init__(self, registry: AutomationToolRegistry, ctx_factory: Any) -> None:
        self._registry = registry
        self._ctx_factory = ctx_factory

    def needs_approval(self, tool_name: str, params: dict[str, Any]) -> bool:
        ctx = self._ctx_factory(params=params, approved=False)
        return self._registry.needs_approval(tool_name, ctx)

    def preview(self, tool_name: str, params: dict[str, Any]) -> str:
        ctx = self._ctx_factory(params=params, approved=False)
        return self._registry.preview(tool_name, ctx)

    def run(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        approved: bool,
        summary: str = "",
    ) -> AutomationToolResult:
        ctx = self._ctx_factory(params=params, approved=approved, summary=summary)
        return self._registry.run(tool_name, ctx)
