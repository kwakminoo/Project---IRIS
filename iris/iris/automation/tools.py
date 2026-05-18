"""컴퓨터 자동화 Tool 구현체."""

from __future__ import annotations

import re
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from urllib.parse import quote_plus

from iris.assistant.safety_guard import ActionRequest, evaluate
from iris.automation import keyboard_mouse_controller, process_launcher, window_controller
from iris.automation.tool_types import (
    AutomationToolContext,
    AutomationToolResult,
    RiskLevel,
    requires_approval_for,
)
from iris.monitoring import ocr_engine, screen_capture


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
    description = "URL을 기본 브라우저에서 열기"
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
        try:
            import webbrowser

            webbrowser.open(url)
            return AutomationToolResult(True, "브라우저에서 URL을 열었습니다.", url)
        except Exception as e:
            return AutomationToolResult(False, str(e))


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
        cap = screen_capture.capture_full_screen(settings)
        if not cap:
            return AutomationToolResult(False, "화면 캡처 실패")
        raw = ocr_engine.ocr_image(settings, cap)
        summary, _ = ocr_engine.ocr_for_storage(settings, raw)
        if not summary.strip():
            return AutomationToolResult(False, "화면에서 텍스트를 읽지 못했습니다.")
        return AutomationToolResult(True, "화면 요약", summary)


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


def all_automation_tools() -> List[AutomationTool]:
    return [
        ListOpenWindowsTool(),
        LaunchAppTool(),
        FocusWindowTool(),
        OpenUrlTool(),
        SearchWebTool(),
        ReadScreenSummaryTool(),
        TypeTextTool(),
        ClickTool(),
        RunShellTool(),
    ]
