"""플랜 실행 + 모니터링 레지스트리 훅."""

from __future__ import annotations

import json
from typing import Callable, Dict, Optional

from iris.assistant.safety_guard import ActionRequest, evaluate
from iris.assistant.task_planner import TaskPlan
from iris.automation import layout_engine, process_launcher, window_controller
from iris.config.preset_modes import PresetMode
from iris.storage.database import Database

# 앱 키 -> 창 제목 부분 문자열 (휴리스틱)
_TITLE_HINT: Dict[str, str] = {
    "chrome": "Chrome",
    "edge": "Edge",
    "code": "Cursor",
    "python": "Windows Terminal",
    "discord": "Discord",
    "steam": "Steam",
    "league": "League",
    "obs": "OBS",
}


class ActionExecutor:
    """순차 실행. 배치 실패는 경고만."""

    def __init__(
        self,
        db: Database,
        app_paths: Dict[str, str],
        register_target: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._db = db
        self._app_paths = app_paths
        self._register_target = register_target

    def execute_plan(self, plan: TaskPlan, preset: PresetMode, approved: bool) -> str:
        """승인된 플랜만 실행."""
        summary = f"execute preset={preset.id} apps={plan.launches}"
        res = evaluate(ActionRequest(summary=summary, approved=approved))
        if not res.allowed:
            self._db.insert_log("action", summary, res.reason)
            return res.reason
        if not approved:
            msg = "승인되지 않아 실행하지 않았습니다."
            self._db.insert_log("action", summary, msg)
            return msg

        lines: list[str] = []
        for step in plan.launches:
            ok, reason = process_launcher.launch_by_key(self._app_paths, step.app_key)
            self._db.insert_action("launch", step.app_key, True, reason)
            if ok:
                lines.append(f"{step.app_key}: 시작")
                hint = _TITLE_HINT.get(step.app_key, step.app_key)
                if self._register_target:
                    self._register_target(step.app_key, hint)
            else:
                lines.append(f"{step.app_key}: 실패 ({reason})")

        for lay in plan.layouts:
            rect = layout_engine.rect_for_hint(lay.hint)
            title_sub = _TITLE_HINT.get(lay.app_key, lay.app_key)
            ok, reason = window_controller.focus_and_place(
                title_sub, rect.left, rect.top, rect.width, rect.height
            )
            if ok:
                lines.append(f"배치 {lay.app_key}: ok")
            else:
                self._db.insert_log("warning", f"layout {lay.app_key}", reason)
                lines.append(f"배치 {lay.app_key}: 경고 {reason}")

        self._db.upsert_recent_work(
            title=preset.title,
            work_type=preset.category.value,
            apps=json.dumps([s.app_key for s in plan.launches], ensure_ascii=False),
            layout=preset.id,
            notes=None,
        )
        return "\n".join(lines)
