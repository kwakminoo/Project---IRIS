"""모니터링 등록 타깃 힌트 — Computer Use perceive 시 짧은 컨텍스트 주입."""

from __future__ import annotations

from typing import Any, List


def list_monitor_target_hints(db: Any) -> List[dict[str, str]]:
    """enabled 타깃의 title/process_name 목록."""
    if db is None or not hasattr(db, "list_targets"):
        return []
    try:
        rows = db.list_targets(enabled_only=True)
    except Exception:
        return []
    out: List[dict[str, str]] = []
    for row in rows:
        title = str(row["title"] if "title" in row.keys() else "") or ""
        proc = str(row["process_name"] if "process_name" in row.keys() else "") or ""
        if title or proc:
            out.append({"title": title, "process_name": proc})
    return out


def match_monitor_hint(
    hints: List[dict[str, str]],
    window_title_sub: str,
) -> str:
    """창 제목이 모니터링 타깃과 겹치면 1줄 힌트."""
    sub = (window_title_sub or "").strip().lower()
    if not sub or not hints:
        return ""
    for h in hints:
        title = (h.get("title") or "").lower()
        proc = (h.get("process_name") or "").lower()
        if sub in title or (title and title in sub) or (proc and proc in sub):
            parts = [p for p in (h.get("title"), h.get("process_name")) if p]
            return f"[monitor_target: {' / '.join(parts)}]"
    return ""
