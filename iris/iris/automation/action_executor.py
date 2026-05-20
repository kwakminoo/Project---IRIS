"""플랜 실행·단일 의도 실행·모니터링 레지스트리 훅."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from iris.assistant.external_agent_adapter import (
    build_external_backend,
    log_external_delegate,
    run_external_delegate,
    tier4_delegate_active,
    user_facing_tier4_line,
)
from iris.assistant.safety_guard import ActionRequest, evaluate
from iris.assistant.task_planner import TaskPlan
from iris.automation import layout_engine, process_launcher, window_controller
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolContext
from iris.config.preset_modes import LayoutHint, PresetMode
from iris.config.settings import Settings
from iris.core.command_router import CommandKind
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


@dataclass(frozen=True)
class IrisExecutionRequest:
    """Safety Guard 통과 후 실행기로 전달되는 단일 요청."""

    command_kind: CommandKind
    user_text: str
    summary: str
    approved: bool
    app_key: str | None = None
    display_name: str | None = None


class ActionExecutor:
    """순차 실행. Tier 4 외부 에이전트는 로컬 실패 시에만(external_agent_adapter)."""

    def __init__(
        self,
        db: Database,
        app_paths: Dict[str, str],
        register_target: Optional[Callable[[str, str], None]] = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._app_paths = app_paths
        self._register_target = register_target
        self._settings = settings
        self._tool_registry = AutomationToolRegistry(db)

    @property
    def tool_registry(self) -> AutomationToolRegistry:
        return self._tool_registry

    def update_app_paths(self, app_paths: Dict[str, str]) -> None:
        """런타임 앱 인덱스 갱신 (동일 dict 참조 유지)."""
        self._app_paths.clear()
        self._app_paths.update(app_paths)

    def run_automation_tool(
        self,
        tool_name: str,
        params: dict,
        *,
        approved: bool,
        summary: str = "",
        settings: object | None = None,
    ) -> str:
        """AutomationToolRegistry 실행 래퍼."""
        ctx = AutomationToolContext(
            params=params,
            approved=approved,
            auto_approve_low_risk=self._db.get_auto_approve_low_risk(),
            app_paths=self._app_paths,
            settings=settings,
            summary=summary or tool_name,
        )
        if self._tool_registry.needs_approval(tool_name, ctx) and not approved:
            preview = self._tool_registry.preview(tool_name, ctx)
            return f"승인 필요: {preview}"
        res = self._tool_registry.run(tool_name, ctx)
        return res.message if res.success else f"실패: {res.message}"

    def execute_iris_request(self, req: IrisExecutionRequest) -> str:
        """Safety → 백엔드 선택 → SQLite 기록."""
        res = evaluate(ActionRequest(summary=req.summary, approved=req.approved))
        if not res.allowed:
            self._db.insert_log("action_exec", req.summary, res.reason)
            return res.reason
        if not req.approved:
            msg = "승인되지 않아 실행하지 않았습니다."
            self._db.insert_log("action_exec", req.summary, msg)
            return msg

        lines: list[str] = []
        backend = "iris_automation"

        if req.command_kind is CommandKind.APP_LAUNCH and req.app_key:
            line, backend = self._run_app_launch(req)
            lines.append(line)

        elif req.command_kind is CommandKind.WINDOW_CONTROL:
            lines.append(self._run_window_control(req.user_text))
            backend = "iris_automation"

        elif req.command_kind is CommandKind.FILE_TASK:
            line, backend = self._run_file_task(req.user_text)
            lines.append(line)

        elif req.command_kind is CommandKind.COMPLEX_AUTOMATION:
            line, backend = self._run_complex_automation(req.user_text)
            lines.append(line)

        else:
            lines.append("지원하지 않는 실행 유형입니다.")
            backend = "none"

        detail = "\n".join(lines)
        self._db.insert_log(
            "action_exec",
            f"{req.command_kind.name}|backend={backend}",
            detail,
        )
        self._db.insert_action("iris_execution", req.summary, True, detail)
        return detail

    def _tier4_delegate(
        self,
        *,
        goal: str,
        context: str,
    ) -> tuple[bool, str] | None:
        """Tier4 활성 시 (성공여부, 사용자용 한국어) 반환. 비활성 시 None."""
        if not isinstance(self._settings, Settings) or not tier4_delegate_active(self._settings):
            return None
        backend = build_external_backend(self._settings)
        if backend is None or not backend.is_available():
            return None
        res, duration_ms = run_external_delegate(backend, goal=goal, context=context)
        user_line = user_facing_tier4_line(res.success)
        log_external_delegate(
            self._db,
            goal=goal,
            backend=res.backend_id,
            success=res.success,
            duration_ms=duration_ms,
            summary_ko=user_line,
        )
        return res.success, user_line

    def _run_app_launch(self, req: IrisExecutionRequest) -> tuple[str, str]:
        assert req.app_key
        ok, reason = process_launcher.launch_by_key(self._app_paths, req.app_key)
        self._db.insert_action("launch", req.app_key, True, reason)
        name = req.display_name or req.app_key
        if ok:
            hint = _TITLE_HINT.get(req.app_key, req.app_key)
            if self._register_target:
                self._register_target(req.app_key, hint)
            return f"{name}: 시작 ({reason})", "iris_automation"

        tier4 = self._tier4_delegate(
            goal=f"애플리케이션 실행: {name}",
            context=f"로컬 실행 실패 사유: {reason}",
        )
        if tier4 is not None:
            ok_t4, msg = tier4
            tag = "tier4" if ok_t4 else "tier4_failed"
            return f"{name}: {msg}", tag

        return f"{name}: 실행 실패 ({reason})", "iris_automation_failed"

    def _run_window_control(self, user_text: str) -> str:
        title_sub = _guess_window_title(user_text)
        hint = LayoutHint(left=0.02, top=0.05, width=0.72, height=0.88, monitor_index=0)
        r = layout_engine.rect_for_hint(hint)
        ok, reason = window_controller.focus_and_place(title_sub, r.left, r.top, r.width, r.height)
        if ok:
            return f"창 제어: '{title_sub}' 포커스·배치 완료"
        return f"창 제어: 실패 ({reason})"

    def _run_file_task(self, user_text: str) -> tuple[str, str]:
        local = self._local_file_search(user_text)
        if local:
            return f"로컬 검색 결과:\n{local}", "local_search"
        tier4 = self._tier4_delegate(
            goal="파일 검색·열기",
            context=f"사용자 요청: {user_text[:800]}",
        )
        if tier4 is not None:
            ok_t4, msg = tier4
            tag = "tier4" if ok_t4 else "tier4_failed"
            return f"파일 작업: {msg}", tag
        return "파일을 찾지 못했고 보조 경로를 사용할 수 없습니다.", "none"

    def _run_complex_automation(self, user_text: str) -> tuple[str, str]:
        tier4 = self._tier4_delegate(
            goal="복잡한 PC 자동화",
            context=f"사용자 요청: {user_text[:800]}",
        )
        if tier4 is not None:
            ok_t4, msg = tier4
            tag = "tier4" if ok_t4 else "tier4_failed"
            return f"자동화: {msg}", tag
        return "자동화: 보조 경로를 사용할 수 없어 실행하지 못했습니다.", "none"

    def _local_file_search(self, user_text: str) -> str | None:
        """제한된 범위에서 파일명 부분 일치 검색."""
        tokens = re.findall(r"[\w가-힣]{2,}", user_text)
        skip = {"어제", "오늘", "작업", "한", "파일", "찾아", "찾아줘", "검색", "문서", "열어줘"}
        keywords = [t for t in tokens if t not in skip and len(t) >= 2]
        if "제안서" in user_text:
            keywords.append("제안서")

        roots = [
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
        ]
        hits: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            try:
                for p in root.rglob("*"):
                    if len(hits) >= 20:
                        break
                    if not p.is_file():
                        continue
                    name = p.name.lower()
                    if any(k.lower() in name for k in keywords):
                        hits.append(p)
            except OSError:
                continue
            if len(hits) >= 20:
                break

        if not hits:
            return None
        lines = [str(p) for p in hits[:15]]
        return "\n".join(lines)

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
        self._db.insert_log("action_exec", summary, "\n".join(lines))
        return "\n".join(lines)


def _guess_window_title(user_text: str) -> str:
    t = user_text.lower()
    if "커서" in user_text or "cursor" in t:
        return "Cursor"
    if "크롬" in user_text or "chrome" in t:
        return "Chrome"
    if "엣지" in user_text or "edge" in t:
        return "Edge"
    if "디스코드" in user_text or "discord" in t:
        return "Discord"
    if "터미널" in user_text or "terminal" in t or "powershell" in t:
        return "Windows Terminal"
    return "Cursor"
