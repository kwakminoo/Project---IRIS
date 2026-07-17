"""코딩 응답 → 파일 반영 오케스트레이션.

젬마 응답에서 파일 제안을 추출하고, 파일마다 승인을 받은 뒤(승인 콜백),
승인된 것만 워크스페이스에 안전하게 쓴다.
UI/모델과 분리된 조립 로직 — 승인은 콜백으로, 파일 쓰기는 automation 계층으로 위임한다.
"""

from __future__ import annotations

from typing import Any, Callable

from iris.assistant.code_proposal import parse_code_proposals
from iris.automation.code_file_writer import (
    PathSafetyError,
    PendingFileWrite,
    commit_file_write,
    plan_file_write,
)

# 승인 콜백: PendingFileWrite를 받아 사용자가 승인하면 True 반환
ApproveFn = Callable[[PendingFileWrite], bool]


def apply_code_from_reply(
    reply: str,
    workspace_root: str | None,
    approve: ApproveFn,
    *,
    database: Any = None,
) -> str:
    """응답의 파일 제안을 반영하고 결과 요약(한국어)을 돌려준다.

    반영할 제안이 없으면 빈 문자열을 반환한다(호출 측은 이 경우 아무것도 덧붙이지 않음).
    CRITICAL_RISK 정책에 따라 각 파일은 approve 콜백 승인 후에만 쓰인다.
    """
    proposals = parse_code_proposals(reply)
    if not proposals:
        return ""
    if not workspace_root:
        return "⚠️ IDE 워크스페이스가 열려 있지 않아 파일을 반영할 수 없습니다."

    lines: list[str] = []
    for prop in proposals:
        try:
            pending = plan_file_write(workspace_root, prop.path, prop.content)
        except PathSafetyError as exc:
            lines.append(f"⛔ {prop.path}: {exc}")
            continue
        if not approve(pending):
            lines.append(f"↩️ {pending.rel_path}: 취소했습니다.")
            continue
        result = commit_file_write(pending, database=database, approved=True)
        mark = "✅" if result.success else "⚠️"
        lines.append(f"{mark} {result.message}")
    return "\n".join(lines)
