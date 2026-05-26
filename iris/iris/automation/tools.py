"""컴퓨터 자동화 Tool 구현체."""

from __future__ import annotations

import re
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from urllib.parse import quote_plus

from iris.assistant.safety_guard import ActionRequest, evaluate
from iris.automation import keyboard_mouse_controller, process_launcher, uia_reader, window_controller
from iris.automation.system_info import (
    collect_system_info,
    system_info_brief_korean,
    system_info_to_json,
    verify_system_info_nonempty,
)
from iris.automation.perception_types import PerceptionObservation
from iris.automation.tool_types import (
    AutomationToolContext,
    AutomationToolResult,
    RiskLevel,
    requires_approval_for,
)
from iris.config.settings import Settings
from iris.monitoring import ocr_engine, screen_capture
from iris.monitoring.target_hints import list_monitor_target_hints, match_monitor_hint
from iris.monitoring.vlm_adapter import StubVlmAdapter


def read_screen_summary_text(settings: Settings) -> tuple[bool, str, str]:
    """전체 화면 OCR 요약 (성공, message, summary)."""
    cap = screen_capture.capture_full_screen(settings)
    if not cap:
        return False, "화면 캡처 실패", ""
    raw = ocr_engine.ocr_image(settings, cap)
    summary, _ = ocr_engine.ocr_for_storage(settings, raw)
    if not summary.strip():
        return False, "화면에서 텍스트를 읽지 못했습니다.", ""
    return True, "화면 요약", summary


def build_perception_observation(ctx: AutomationToolContext) -> PerceptionObservation:
    """perceive_desktop 파이프라인: UIA → OCR → (선택) VLM."""
    settings = ctx.settings
    if settings is None:
        return PerceptionObservation(summary="설정 없음", perception_source="unknown")

    focus_hint = str(ctx.params.get("focus_hint") or "").strip()
    title_sub = str(ctx.params.get("window_title_sub") or "").strip()
    prefer_window_only = bool(ctx.params.get("prefer_window_only"))

    if focus_hint:
        window_controller.focus_and_place(focus_hint, 40, 40, 1100, 720)

    active = window_controller.get_active_window_title()
    if not title_sub:
        title_sub = active or focus_hint

    obs = PerceptionObservation(active_window=active or title_sub)
    uia_enabled = bool(getattr(settings, "computer_use_uia_enabled", True))
    vlm_enabled = bool(getattr(settings, "computer_use_vlm_enabled", False))

    uia_json = ""
    if uia_enabled and title_sub:
        _, uia_json, matched = uia_reader.snapshot_window_uia(title_sub)
        if matched:
            obs.active_window = matched

    if uia_json and not uia_reader.is_uia_summary_sparse(uia_json):
        obs.summary = uia_json
        obs.perception_source = "uia"
    elif prefer_window_only:
        # Media play: 전체 화면 OCR 폴백 생략 (Iris/타 창 텍스트 혼입 방지)
        obs.summary = uia_json or ""
        obs.perception_source = "uia" if uia_json else "unknown"
    else:
        ok, msg, ocr_summary = read_screen_summary_text(settings)
        if ok:
            obs.summary = ocr_summary
            obs.perception_source = "ocr" if not uia_json else "hybrid"
        else:
            obs.summary = uia_json or msg
            obs.perception_source = "ocr" if not uia_json else "hybrid"

    if vlm_enabled and obs.perception_source in ("ocr", "hybrid", "uia"):
        cap = screen_capture.capture_full_screen(settings)
        if cap:
            try:
                vlm = StubVlmAdapter()
                scene = vlm.describe_scene(cap.rgb_bytes, cap.width, cap.height)
                if scene.strip():
                    obs.summary = (obs.summary[:1200] + " | VLM: " + scene.strip()[:300]).strip()
                    obs.perception_source = "vlm"
            except Exception:
                pass

    hints = list_monitor_target_hints(ctx.database)
    obs.monitor_hint = match_monitor_hint(hints, title_sub or active)
    if obs.monitor_hint:
        obs.summary = f"{obs.monitor_hint}\n{obs.summary}"[:2000]

    titles = window_controller.list_window_titles()
    if titles:
        obs.open_windows_summary = ", ".join(titles[:12])

    return obs


class AutomationTool(ABC):
    """단일 자동화 도구."""

    name: str
    description: str
    risk_level: RiskLevel

    @property
    def requires_approval(self) -> bool:
        """기본: 위험 등급 기준 (실행 시 컨텍스트로 재계산)."""
        return requires_approval_for(self.risk_level, False)

    def needs_approval(self, ctx: AutomationToolContext) -> bool:
        return requires_approval_for(self.risk_level, ctx.auto_approve_low_risk)

    @abstractmethod
    def preview(self, ctx: AutomationToolContext) -> str:
        ...

    @abstractmethod
    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        ...


class ListOpenWindowsTool(AutomationTool):
    name = "list_open_windows"
    description = "열린 창 제목 목록 조회"
    risk_level = RiskLevel.LOW_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        return "열린 창 제목 목록을 조회합니다."

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        titles = window_controller.list_window_titles()
        if not titles:
            return AutomationToolResult(False, "창 목록을 가져오지 못했습니다.")
        shown = titles[:40]
        body = "\n".join(f"- {t}" for t in shown)
        if len(titles) > 40:
            body += f"\n… 외 {len(titles) - 40}개"
        return AutomationToolResult(True, f"{len(titles)}개 창", body)


class LaunchAppTool(AutomationTool):
    name = "launch_app"
    description = "등록된 앱 실행"
    risk_level = RiskLevel.HIGH_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        key = str(ctx.params.get("app_key") or "")
        disp = str(ctx.params.get("display_name") or key)
        return f"앱 실행: {disp} ({key})"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        key = str(ctx.params.get("app_key") or "")
        if not key:
            return AutomationToolResult(False, "app_key가 필요합니다.")
        ok, reason = process_launcher.launch_by_key(ctx.app_paths, key)
        disp = str(ctx.params.get("display_name") or key)
        if ok:
            return AutomationToolResult(True, f"{disp} 실행 시작", reason)
        return AutomationToolResult(False, f"{disp} 실행 실패", reason)


class FocusWindowTool(AutomationTool):
    name = "focus_window"
    description = "창 제목 일부로 포커스"
    risk_level = RiskLevel.MEDIUM_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        sub = str(ctx.params.get("title_sub") or "")
        return f"창 포커스: '{sub}'"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        sub = str(ctx.params.get("title_sub") or "").strip()
        if not sub:
            return AutomationToolResult(False, "title_sub가 필요합니다.")
        ok, reason = window_controller.focus_and_place(sub, 40, 40, 1100, 720)
        return AutomationToolResult(ok, "포커스 완료" if ok else "포커스 실패", reason)


class OpenUrlTool(AutomationTool):
    name = "open_url"
    description = "URL을 Iris 설정의 기본 웹 브라우저에서 열기"
    risk_level = RiskLevel.MEDIUM_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        url = str(ctx.params.get("url") or "")
        return f"URL 열기: {url[:120]}"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        url = str(ctx.params.get("url") or "").strip()
        if not url:
            return AutomationToolResult(False, "url이 필요합니다.")
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        guard = evaluate(ActionRequest(summary=f"open url {url}", approved=ctx.approved))
        if not guard.allowed:
            return AutomationToolResult(False, guard.reason)
        from iris.automation.web_browser import open_url as open_in_browser
        from iris.automation.web_browser import resolve_browser_key

        browser = resolve_browser_key(ctx.settings)
        ok, msg = open_in_browser(url, browser, ctx.app_paths)
        if ok:
            return AutomationToolResult(True, msg, url)
        return AutomationToolResult(False, msg)


class GetSystemInfoTool(AutomationTool):
    name = "get_system_info"
    description = "CPU/RAM/GPU/디스크/OS 요약 (로컬 조회)"
    risk_level = RiskLevel.LOW_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        return "시스템 사양·리소스를 요약 조회합니다."

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        info = collect_system_info()
        if not verify_system_info_nonempty(info):
            return AutomationToolResult(
                False,
                "시스템 정보를 충분히 읽지 못했습니다.",
                system_info_to_json(info),
            )
        brief = system_info_brief_korean(info)
        return AutomationToolResult(True, brief, system_info_to_json(info))


class SearchWebTool(AutomationTool):
    name = "search_web"
    description = "웹 검색 URL 열기 (Playwright 검색은 UI 워커)"
    risk_level = RiskLevel.MEDIUM_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        q = str(ctx.params.get("query") or "")
        return f"웹 검색: {q[:100]}"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        q = str(ctx.params.get("query") or "").strip()
        if not q:
            return AutomationToolResult(False, "query가 필요합니다.")
        url = "https://www.google.com/search?q=" + quote_plus(q)
        sub_ctx = AutomationToolContext(
            params={"url": url},
            approved=ctx.approved,
            auto_approve_low_risk=ctx.auto_approve_low_risk,
        )
        return OpenUrlTool().execute(sub_ctx)


class ReadScreenSummaryTool(AutomationTool):
    name = "read_screen_summary"
    description = "현재 화면 OCR 요약 (원문 저장 없음)"
    risk_level = RiskLevel.LOW_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        return "현재 화면을 요약해 읽습니다 (원문은 저장하지 않음)."

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        settings = ctx.settings
        if settings is None:
            return AutomationToolResult(False, "설정이 없어 화면 요약을 할 수 없습니다.")
        ok, msg, summary = read_screen_summary_text(settings)
        if not ok:
            return AutomationToolResult(False, msg)
        return AutomationToolResult(True, msg, summary)


class TypeTextTool(AutomationTool):
    name = "type_text"
    description = "승인된 키보드 입력"
    risk_level = RiskLevel.HIGH_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        text = str(ctx.params.get("text") or "")
        shown = text if len(text) <= 40 else text[:40] + "…"
        return f"키보드 입력: '{shown}'"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        text = str(ctx.params.get("text") or "")
        guard = evaluate(ActionRequest(summary=f"type text {text[:80]}", approved=ctx.approved))
        if not guard.allowed:
            return AutomationToolResult(False, guard.reason)
        ok, reason = keyboard_mouse_controller.type_text_approved(text, approved=True)
        return AutomationToolResult(ok, "입력 완료" if ok else "입력 실패", reason)


class ClickTool(AutomationTool):
    name = "click"
    description = "승인된 마우스 클릭"
    risk_level = RiskLevel.HIGH_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        x = ctx.params.get("x")
        y = ctx.params.get("y")
        return f"마우스 클릭: ({x}, {y})"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        try:
            x = int(ctx.params.get("x", 0))
            y = int(ctx.params.get("y", 0))
            import pyautogui  # type: ignore

            pyautogui.click(x, y)
            return AutomationToolResult(True, f"클릭 ({x},{y})")
        except Exception as e:
            return AutomationToolResult(False, str(e))


_DANGEROUS_SHELL = re.compile(
    r"(rm\s+-rf|del\s+/s|format\s|shutdown|registry|curl\s+\|?\s*bash|powershell\s+-enc)",
    re.IGNORECASE,
)


class RunShellTool(AutomationTool):
    name = "run_shell"
    description = "승인된 쉘 명령 (위험 패턴 차단)"
    risk_level = RiskLevel.CRITICAL_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        cmd = str(ctx.params.get("command") or "")
        shown = cmd if len(cmd) <= 80 else cmd[:80] + "…"
        return f"쉘 실행: {shown}"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        cmd = str(ctx.params.get("command") or "").strip()
        if not cmd:
            return AutomationToolResult(False, "command가 필요합니다.")
        guard = evaluate(ActionRequest(summary=cmd, approved=ctx.approved))
        if not guard.allowed:
            return AutomationToolResult(False, guard.reason)
        if _DANGEROUS_SHELL.search(cmd):
            return AutomationToolResult(False, "위험한 쉘 명령은 차단됩니다.")
        if not ctx.approved:
            return AutomationToolResult(False, "사용자 승인이 필요합니다.")
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = (proc.stdout or "")[:2000]
            err = (proc.stderr or "")[:500]
            detail = out or err or f"exit={proc.returncode}"
            ok = proc.returncode == 0
            return AutomationToolResult(ok, "쉘 완료" if ok else f"exit {proc.returncode}", detail)
        except subprocess.TimeoutExpired:
            return AutomationToolResult(False, "쉘 명령 시간 초과")
        except Exception as e:
            return AutomationToolResult(False, str(e))


class UiaSnapshotTool(AutomationTool):
    name = "uia_snapshot"
    description = "창 UIA 트리 요약 JSON (2KB 이하)"
    risk_level = RiskLevel.LOW_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        sub = str(ctx.params.get("window_title_sub") or "")
        return f"UIA 스냅샷: '{sub}'"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        settings = ctx.settings
        if settings is None:
            return AutomationToolResult(False, "설정이 없습니다.")
        if not getattr(settings, "computer_use_uia_enabled", True):
            return AutomationToolResult(False, "UIA가 비활성화되어 있습니다.")
        sub = str(ctx.params.get("window_title_sub") or "").strip()
        if not sub:
            sub = window_controller.get_active_window_title()
        if not sub:
            return AutomationToolResult(False, "window_title_sub가 필요합니다.")
        _, json_text, matched = uia_reader.snapshot_window_uia(sub)
        if not json_text:
            return AutomationToolResult(
                False,
                "UIA 스냅샷 실패 (pywinauto 없음 또는 창 없음). perceive_desktop 또는 read_screen_summary를 사용하세요.",
            )
        return AutomationToolResult(True, f"UIA: {matched or sub}", json_text)


class PerceiveDesktopTool(AutomationTool):
    name = "perceive_desktop"
    description = "하이브리드 데스크톱 인식 (UIA 우선, OCR/VLM 보조)"
    risk_level = RiskLevel.LOW_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        return "활성 창·UIA·OCR로 데스크톱 상태를 요약합니다."

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        if ctx.settings is None:
            return AutomationToolResult(False, "설정이 없습니다.")
        obs = build_perception_observation(ctx)
        return AutomationToolResult(
            True,
            obs.to_observation_string(max_summary=400),
            obs.to_detail_json(),
        )


class UiaClickTool(AutomationTool):
    name = "uia_click"
    description = "UIA 요소 name/automation_id로 클릭"
    risk_level = RiskLevel.HIGH_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        sub = str(ctx.params.get("window_title_sub") or "")
        name = str(ctx.params.get("name") or "")
        return f"UIA 클릭: '{sub}' / '{name}'"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        settings = ctx.settings
        if settings is None:
            return AutomationToolResult(False, "설정이 없습니다.")
        if not getattr(settings, "computer_use_uia_enabled", True):
            return AutomationToolResult(
                False,
                "UIA 비활성. send_hotkey 또는 click(x,y)를 사용하세요.",
            )
        guard = evaluate(
            ActionRequest(
                summary=f"uia_click {ctx.params}",
                approved=ctx.approved,
            )
        )
        if not guard.allowed:
            return AutomationToolResult(False, guard.reason)
        sub = str(ctx.params.get("window_title_sub") or "").strip()
        if not sub:
            sub = window_controller.get_active_window_title()
        ok, reason = uia_reader.click_uia_element(
            sub,
            name=str(ctx.params.get("name") or ""),
            automation_id=str(ctx.params.get("automation_id") or ""),
        )
        return AutomationToolResult(ok, "UIA 클릭" if ok else "UIA 클릭 실패", reason)


class SendHotkeyTool(AutomationTool):
    name = "send_hotkey"
    description = "단축키 조합 (예: ctrl+f)"
    risk_level = RiskLevel.HIGH_RISK

    def preview(self, ctx: AutomationToolContext) -> str:
        keys = ctx.params.get("keys") or []
        return f"단축키: {'+'.join(str(k) for k in keys)}"

    def execute(self, ctx: AutomationToolContext) -> AutomationToolResult:
        raw = ctx.params.get("keys")
        if isinstance(raw, str):
            keys = [k.strip() for k in raw.replace("+", ",").split(",") if k.strip()]
        elif isinstance(raw, list):
            keys = [str(k).strip() for k in raw if str(k).strip()]
        else:
            keys = []
        guard = evaluate(
            ActionRequest(summary=f"hotkey {'+'.join(keys)}", approved=ctx.approved)
        )
        if not guard.allowed:
            return AutomationToolResult(False, guard.reason)
        ok, reason = keyboard_mouse_controller.send_hotkey_approved(keys, approved=True)
        return AutomationToolResult(ok, "단축키" if ok else "단축키 실패", reason)


def all_automation_tools() -> List[AutomationTool]:
    return [
        GetSystemInfoTool(),
        ListOpenWindowsTool(),
        LaunchAppTool(),
        FocusWindowTool(),
        OpenUrlTool(),
        SearchWebTool(),
        ReadScreenSummaryTool(),
        UiaSnapshotTool(),
        PerceiveDesktopTool(),
        TypeTextTool(),
        ClickTool(),
        UiaClickTool(),
        SendHotkeyTool(),
        RunShellTool(),
    ]
