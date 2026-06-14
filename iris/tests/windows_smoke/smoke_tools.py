"""스모크 테스트 전용 승인 도구 — 실제 위험 작업 없음."""

from __future__ import annotations

from pathlib import Path

from iris.automation.tool_types import AutomationToolContext, AutomationToolResult, RiskLevel
from iris.automation.tools import AutomationTool

# 모듈 레벨 카운터 — 승인 전 미실행 검증용
_EXECUTION_COUNT = 0


def reset_smoke_execution_count() -> None:
    global _EXECUTION_COUNT
    _EXECUTION_COUNT = 0


def smoke_execution_count() -> int:
    return _EXECUTION_COUNT


class SmokeRequiresApprovalTool(AutomationTool):
    """CRITICAL 승인 경로 검증 — 임시 marker 파일만 생성."""

    name = "smoke_requires_approval"
    description = "스모크 테스트용 승인 도구 (marker 파일 생성)"
    risk_level = RiskLevel.CRITICAL_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        marker = str(ctx.params.get("marker") or "smoke")
        return f"스모크 marker 파일 생성: {marker}"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        global _EXECUTION_COUNT
        if not ctx.approved:
            return AutomationToolResult(False, "승인 필요")
        marker = str(ctx.params.get("marker") or "smoke")
        out_dir = Path(str(ctx.params.get("output_dir") or "."))
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{marker}.txt"
        path.write_text(marker, encoding="utf-8")
        _EXECUTION_COUNT += 1
        return AutomationToolResult(True, "marker_created", str(path))
