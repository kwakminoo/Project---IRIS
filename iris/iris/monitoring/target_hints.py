"""모니터링 등록 타깃 힌트 — Computer Use perceive 시 짧은 컨텍스트 주입."""

from __future__ import annotations

import json
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


def match_monitor_target(
    hints: List[dict[str, str]],
    window_title_sub: str,
) -> dict[str, str] | None:
    """창 제목이 모니터링 타깃과 겹치면 구조화 dict."""
    sub = (window_title_sub or "").strip().lower()
    if not sub or not hints:
        return None
    for h in hints:
        title = (h.get("title") or "").lower()
        proc = (h.get("process_name") or "").lower()
        if sub in title or (title and title in sub) or (proc and proc in sub):
            return {
                "title": h.get("title") or "",
                "process_name": h.get("process_name") or "",
            }
    return None


def build_perceive_monitor_hint_json(
    hints: List[dict[str, str]],
    window_title_sub: str,
) -> str:
    """perceive_desktop detail.monitor_hint — JSON 문자열 (없으면 빈 문자열)."""
    matched = match_monitor_target(hints, window_title_sub)
    if not matched:
        return ""
    payload = {
        "source": "target_match",
        "target_title": matched.get("title") or "",
        "process_name": matched.get("process_name") or "",
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def match_monitor_hint(
    hints: List[dict[str, str]],
    window_title_sub: str,
) -> str:
    """레거시 1줄 문자열 — summary 혼입용 (신규 코드는 build_perceive_monitor_hint_json 사용)."""
    matched = match_monitor_target(hints, window_title_sub)
    if not matched:
        return ""
    parts = [p for p in (matched.get("title"), matched.get("process_name")) if p]
    return f"[monitor_target: {' / '.join(parts)}]"
