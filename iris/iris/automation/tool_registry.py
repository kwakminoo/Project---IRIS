"""컴퓨터 자동화 ToolRegistry (assistant/tool_registry.py 와 분리)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from iris.automation.tool_types import AutomationToolContext, AutomationToolResult
from iris.automation.tools import AutomationTool, all_automation_tools

if TYPE_CHECKING:
    from iris.storage.database import Database


class AutomationToolRegistry:
    """등록된 자동화 도구 실행·미리보기·승인 판단."""

    def __init__(self, db: Optional["Database"] = None) -> None:
        self._db = db
        self._tools: Dict[str, AutomationTool] = {t.name: t for t in all_automation_tools()}

    def get(self, name: str) -> AutomationTool | None:
        return self._tools.get(name)

    def register_tool(self, tool: AutomationTool) -> None:
        """테스트·확장용 도구 등록 (동일 name은 덮어씀)."""
        self._tools[tool.name] = tool

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def preview(self, name: str, ctx: AutomationToolContext) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"알 수 없는 도구: {name}"
        return tool.preview(ctx)

    def needs_approval(self, name: str, ctx: AutomationToolContext) -> bool:
        tool = self._tools.get(name)
        if tool is None:
            return True
        return tool.needs_approval(ctx)

    def run(self, name: str, ctx: AutomationToolContext) -> AutomationToolResult:
        """승인·로깅 후 실행."""
        tool = self._tools.get(name)
        if tool is None:
            return AutomationToolResult(False, f"알 수 없는 도구: {name}")

        if tool.needs_approval(ctx) and not ctx.approved:
            msg = "사용자 승인이 필요합니다."
            self._log_tool(name, ctx, False, msg)
            return AutomationToolResult(False, msg)

        preview = tool.preview(ctx)
        result = tool.execute(ctx)
        self._log_tool(name, ctx, result.success, result.message, preview, result.detail)
        return result

    def _log_tool(
        self,
        name: str,
        ctx: AutomationToolContext,
        success: bool,
        message: str,
        preview: str | None = None,
        detail: str | None = None,
    ) -> None:
        if self._db is None:
            return
        body = message
        if detail:
            body = f"{message} | {detail[:800]}"
        self._db.insert_automation_tool_log(
            tool_name=name,
            summary=ctx.summary or preview or name,
            approved=ctx.approved,
            success=success,
            result=body[:2000],
        )
