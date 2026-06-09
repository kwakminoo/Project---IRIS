"""Computer Use용 모니터링 힌트 — DB 이벤트·타깃 상태 → observation 1줄."""

from __future__ import annotations

import json
from typing import Any, Literal

from iris.monitoring.models import StatusCategory
from iris.monitoring.target_hints import list_monitor_target_hints, match_monitor_target

MonitorHintSource = Literal["target_match", "target_status", "recent_event"]


def _row_val(row: Any, key: str, default: str = "") -> str:
    if row is None:
        return default
    try:
        return str(row[key] if key in row.keys() else default) or default
    except (KeyError, TypeError, AttributeError):
        return default


def _window_matches_title(window_sub: str, title: str) -> bool:
    sub = (window_sub or "").strip().lower()
    t = (title or "").strip().lower()
    if not sub or not t:
        return False
    return sub in t or t in sub


def _find_matched_target(
    db: Any,
    *,
    active_window_title: str,
    active_process_name: str,
) -> dict[str, Any] | None:
    """활성 창과 겹치는 enabled 모니터링 타깃 1건."""
    if db is None or not hasattr(db, "list_targets"):
        return None
    try:
        rows = db.list_targets(enabled_only=True)
    except Exception:
        return None
    sub = (active_window_title or active_process_name or "").strip()
    if not sub:
        return None
    hints = list_monitor_target_hints(db)
    matched = match_monitor_target(hints, sub)
    if not matched:
        return None
    title_key = matched.get("title") or ""
    proc_key = matched.get("process_name") or ""
    for row in rows:
        title = _row_val(row, "title")
        proc = _row_val(row, "process_name")
        if title == title_key and proc == proc_key:
            return {
                "source": "target_match",
                "target_id": int(row["id"]),
                "target_title": title,
                "process_name": proc,
                "category": _row_val(row, "status", StatusCategory.UNKNOWN.value),
                "reason": "",
                "recommended_action": _row_val(row, "last_event")[:240],
            }
    return {
        "source": "target_match",
        "target_id": None,
        "target_title": title_key,
        "process_name": proc_key,
        "category": StatusCategory.UNKNOWN.value,
        "reason": "",
        "recommended_action": "",
    }


def _target_status_hint(db: Any, target_id: int | None) -> dict[str, Any] | None:
    """recent_target_states — 비정상 상태만."""
    if db is None or target_id is None or not hasattr(db, "get_recent_target_state"):
        return None
    try:
        rts = db.get_recent_target_state(target_id)
    except Exception:
        return None
    if rts is None:
        return None
    cat = _row_val(rts, "status", StatusCategory.UNKNOWN.value)
    if cat in (StatusCategory.NORMAL.value, StatusCategory.UNKNOWN.value):
        return None
    return {
        "source": "target_status",
        "target_id": target_id,
        "target_title": "",
        "process_name": "",
        "category": cat,
        "reason": f"last_changed={_row_val(rts, 'last_changed_at')[:40]}",
        "recommended_action": "",
    }


def _recent_event_hint(
    db: Any,
    *,
    active_window_title: str,
    limit: int = 8,
) -> dict[str, Any] | None:
    """최근 모니터링 이벤트 1건 — NORMAL/UNKNOWN 제외, 활성 창 우선."""
    if db is None or not hasattr(db, "list_recent_events"):
        return None
    try:
        rows = db.list_recent_events(limit=limit)
    except Exception:
        return None
    candidates: list[dict[str, Any]] = []
    for row in rows:
        cat = _row_val(row, "category")
        if cat in (StatusCategory.NORMAL.value, StatusCategory.UNKNOWN.value):
            continue
        evt = {
            "source": "recent_event",
            "target_id": int(row["target_id"]) if row["target_id"] is not None else None,
            "target_title": _row_val(row, "target_title")[:120],
            "process_name": "",
            "category": cat,
            "reason": _row_val(row, "reason")[:240],
            "recommended_action": _row_val(row, "recommended_action")[:240],
            "event_id": int(row["id"]),
        }
        candidates.append(evt)
    if not candidates:
        return None
    for evt in candidates:
        if _window_matches_title(active_window_title, evt["target_title"]):
            return evt
    return candidates[0]


def collect_monitor_hints(
    db: Any,
    *,
    active_window_title: str = "",
    active_process_name: str = "",
    perceive_monitor_hint: str = "",
) -> list[dict[str, Any]]:
    """모니터링 DB·perceive detail에서 CU용 구조화 힌트 수집 (최대 3건)."""
    hints: list[dict[str, Any]] = []

    if perceive_monitor_hint.strip():
        try:
            parsed = json.loads(perceive_monitor_hint)
            if isinstance(parsed, dict):
                hints.append(parsed)
        except json.JSONDecodeError:
            pass

    matched = _find_matched_target(
        db,
        active_window_title=active_window_title,
        active_process_name=active_process_name,
    )
    if matched and not any(h.get("source") == "target_match" for h in hints):
        hints.append(matched)
        status = _target_status_hint(db, matched.get("target_id"))
        if status:
            hints.append(status)

    evt = _recent_event_hint(db, active_window_title=active_window_title)
    if evt and not any(
        h.get("source") == "recent_event" and h.get("event_id") == evt.get("event_id")
        for h in hints
    ):
        hints.append(evt)

    # 중복 source+target_id 제거, 최대 3건
    seen: set[tuple[str, Any]] = set()
    out: list[dict[str, Any]] = []
    for h in hints:
        key = (str(h.get("source") or ""), h.get("target_id"), h.get("event_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= 3:
            break
    return out


def monitor_hint_observation_line(hints: list[dict[str, Any]]) -> str | None:
    """LLM observation 한 줄 — monitor_hint: {...} 또는 monitor_hint: [{...},...]."""
    if not hints:
        return None
    payload: Any = hints[0] if len(hints) == 1 else hints
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(body) > 900:
        body = body[:897] + "..."
    return f"monitor_hint: {body}"


def append_monitor_hint_observations(
    observations: list[str],
    db: Any,
    *,
    active_window_title: str = "",
    active_process_name: str = "",
    perceive_monitor_hint: str = "",
) -> bool:
    """ctx.observations에 monitor_hint 1줄 추가 — 추가 시 True."""
    hints = collect_monitor_hints(
        db,
        active_window_title=active_window_title,
        active_process_name=active_process_name,
        perceive_monitor_hint=perceive_monitor_hint,
    )
    line = monitor_hint_observation_line(hints)
    if not line:
        return False
    observations.append(line)
    return True
