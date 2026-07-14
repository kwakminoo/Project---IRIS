"""Iris Wiki 자동화 도구."""

from __future__ import annotations

from pathlib import Path

from iris.automation.tool_types import AutomationToolContext, AutomationToolResult, RiskLevel
from iris.automation.tools import AutomationTool
from iris.infrastructure.knowledge.vault_repository import default_vault_path


def _get_service(ctx: AutomationToolContext):
    assistant = getattr(ctx, "assistant", None)
    if assistant is not None:
        svc = getattr(assistant, "knowledge_service", None)
        if svc is not None:
            return svc
    from iris.application.knowledge_service import build_knowledge_service
    from iris.config.settings import Settings

    settings: Settings | None = ctx.settings
    vault = default_vault_path()
    if settings and settings.wiki_vault_path:
        vault = Path(settings.wiki_vault_path)
    return build_knowledge_service(ctx.database, vault, settings=settings)


class KnowledgeSearchTool(AutomationTool):
    name = "knowledge_search"
    description = "로컬 Iris Wiki 검색"
    risk_level = RiskLevel.LOW_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        q = str(ctx.params.get("query") or "")
        return f"Iris Wiki 검색: {q}"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        q = str(ctx.params.get("query") or "").strip()
        if not q:
            return AutomationToolResult(False, "query가 필요합니다.")
        svc = _get_service(ctx)
        hits = svc.search(q, limit=int(ctx.params.get("limit") or 6))
        if not hits:
            return AutomationToolResult(True, "검색 결과 없음", "")
        lines = [f"- {h.title} ({h.path})\n  {h.snippet[:200]}" for h in hits]
        return AutomationToolResult(True, f"{len(hits)}건", "\n".join(lines))


class KnowledgeSyncTool(AutomationTool):
    name = "knowledge_sync_sources"
    description = "Knowledge 소스 동기화"
    risk_level = RiskLevel.MEDIUM_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        return "등록된 지식 소스를 동기화합니다."

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        svc = _get_service(ctx)
        report = svc.sync()
        msg = (
            f"indexed={report.indexed} unchanged={report.unchanged} "
            f"skipped={report.skipped} missing={report.missing}"
        )
        return AutomationToolResult(True, "동기화 완료", msg)


class KnowledgeOpenNoteTool(AutomationTool):
    name = "knowledge_open_note"
    description = "인덱싱된 노트 경로 조회"
    risk_level = RiskLevel.LOW_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        return "노트 경로를 반환합니다."

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        path = str(ctx.params.get("path") or "").strip()
        if not path:
            return AutomationToolResult(False, "path가 필요합니다.")
        svc = _get_service(ctx)
        src = svc.index.get_source_by_path(path)
        if src is None:
            return AutomationToolResult(False, "노트를 찾지 못했습니다.")
        body = svc.get_chunk_preview(src.id)
        return AutomationToolResult(True, src.title, f"{src.canonical_path}\n\n{body[:2000]}")


def knowledge_automation_tools() -> list[AutomationTool]:
    return [KnowledgeSearchTool(), KnowledgeSyncTool(), KnowledgeOpenNoteTool()]
