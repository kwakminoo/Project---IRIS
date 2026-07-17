"""워크스페이스 안전 파일 쓰기 — CRITICAL_RISK 액션.

젬마가 생성한 코드를 실제 파일로 반영한다.
Safety Guard 정책상 파일 생성/덮어쓰기는 4단계(CRITICAL) → 명시적 승인 필수이므로,
이 모듈은 '계획(plan) → 승인(호출 측) → 반영(commit)' 순서로만 동작한다.
경로는 워크스페이스 루트 안으로 제한하고, 결과는 SQLite에 로그한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris.automation.tool_types import AutomationToolResult, RiskLevel

# 파일 쓰기 위험 등급 — 항상 승인 필요
RISK = RiskLevel.CRITICAL_RISK


class PathSafetyError(ValueError):
    """워크스페이스 밖이거나 위험한 경로 차단."""


@dataclass
class PendingFileWrite:
    """승인 대기 중인 파일 쓰기 계획."""

    abs_path: Path
    rel_path: str
    content: str
    is_overwrite: bool
    summary: str

    def preview(self, max_chars: int = 2000) -> str:
        """승인 다이얼로그에 보여줄 미리보기 텍스트."""
        body = self.content
        if len(body) > max_chars:
            body = body[:max_chars] + "\n… (이하 생략)"
        head = ("덮어쓰기" if self.is_overwrite else "새 파일") + f": {self.rel_path}"
        return f"{head}\n\n{body}"


def plan_file_write(
    workspace_root: str | Path, rel_path: str, content: str
) -> PendingFileWrite:
    """쓰기 계획을 만들고 경로 안전성을 검증한다. 위험하면 PathSafetyError."""
    root = Path(workspace_root).resolve()
    if not root.exists() or not root.is_dir():
        raise PathSafetyError(f"워크스페이스 경로가 유효하지 않습니다: {workspace_root}")

    rel = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise PathSafetyError("파일 경로가 비어 있습니다.")
    if ".." in Path(rel).parts:
        raise PathSafetyError("상위 디렉터리(..) 접근은 허용되지 않습니다.")

    target = (root / rel).resolve()
    # 워크스페이스 루트 밖이면 차단 (심볼릭 링크 등 우회 방지)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PathSafetyError("워크스페이스 밖 경로에는 쓸 수 없습니다.") from exc

    is_overwrite = target.exists()
    verb = "덮어쓰기" if is_overwrite else "새 파일 생성"
    summary = f"{verb}: {rel} ({len(content)} bytes)"
    return PendingFileWrite(
        abs_path=target,
        rel_path=rel,
        content=content,
        is_overwrite=is_overwrite,
        summary=summary,
    )


def commit_file_write(
    pending: PendingFileWrite, *, database: Any = None, approved: bool = True
) -> AutomationToolResult:
    """승인된 계획을 실제 파일로 반영한다. 예외는 삼켜 앱 크래시를 막고 로그로 남긴다."""
    if not approved:
        _log(database, pending.summary, approved=False, success=False, result="미승인")
        return AutomationToolResult(False, "승인되지 않아 파일을 쓰지 않았습니다.")
    try:
        pending.abs_path.parent.mkdir(parents=True, exist_ok=True)
        pending.abs_path.write_text(pending.content, encoding="utf-8")
    except OSError as exc:
        _log(database, pending.summary, approved=True, success=False, result=str(exc))
        return AutomationToolResult(False, f"파일 쓰기 실패: {exc}")

    _log(database, pending.summary, approved=True, success=True, result=str(pending.abs_path))
    verb = "덮어썼습니다" if pending.is_overwrite else "만들었습니다"
    return AutomationToolResult(
        True, f"{pending.rel_path} 파일을 {verb}.", detail=str(pending.abs_path)
    )


def _log(
    database: Any, summary: str, *, approved: bool, success: bool, result: str
) -> None:
    """automation_tool_logs 기록. 로깅 실패로 기능이 죽지 않도록 방어한다."""
    if database is None:
        return
    try:
        database.insert_automation_tool_log("write_file", summary, approved, success, result)
    except Exception:  # noqa: BLE001 — 로깅 실패는 무시
        pass
