"""Computer Use Perception — 구조화된 PerceptionObservation 빌더."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from iris.automation.tool_types import AutomationToolContext, AutomationToolResult

if TYPE_CHECKING:
    from iris.automation.tool_registry import AutomationToolRegistry
    from iris.config.settings import Settings
    from iris.storage.database import Database

PerceptionSource = Literal["uia", "ocr", "vlm", "hybrid", "unknown"]


@dataclass
class PerceptionObservation:
    """domain-design PerceptionObservation — 한 스텝 PC 상태 요약 (원문 저장 없음)."""

    active_window_title: str = ""
    active_process_name: str = ""
    open_windows_summary: str = ""
    uia_snapshot_summary: str = ""
    scene_summary: str = ""
    perception_source: PerceptionSource = "unknown"
    captured_at: float = 0.0
    raw_tool_results: dict[str, Any] = field(default_factory=dict)


def resolve_active_process_name() -> str:
    """활성 창 프로세스명 (Windows win32+psutil, 실패 시 빈 문자열)."""
    if sys.platform != "win32":
        return ""
    try:
        import psutil  # type: ignore[import-untyped]
        import win32gui  # type: ignore[import-untyped]
        import win32process  # type: ignore[import-untyped]

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ""
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return ""
        return str(psutil.Process(pid).name() or "")
    except Exception:
        return ""


def has_valid_perception(p: PerceptionObservation | None) -> bool:
    """기계 판정 — 최근 perceive 존재 여부 (observation regex 대체)."""
    if p is None:
        return False
    if not p.perception_source or p.perception_source == "unknown":
        return False
    return p.captured_at > 0


def _tool_result_payload(result: AutomationToolResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "message": result.message,
        "detail": result.detail,
    }


def _parse_perceive_detail(detail: str) -> dict[str, Any]:
    if not detail.strip():
        return {}
    try:
        data = json.loads(detail)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _split_summary_by_source(
    summary: str,
    source: PerceptionSource,
) -> tuple[str, str]:
    """perception_source에 따라 UIA·scene 요약 분리."""
    text = summary.strip()
    if not text:
        return "", ""
    if source == "uia":
        return text[:2000], ""
    if source == "ocr":
        return "", text[:2000]
    if source in ("hybrid", "vlm"):
        if " | VLM: " in text:
            base, vlm_part = text.split(" | VLM: ", 1)
            return base[:1200], (base + " | VLM: " + vlm_part)[:2000]
        return text[:1200], text[:2000]
    return "", text[:2000]


def build_perception(
    registry: AutomationToolRegistry,
    settings: Settings,
    *,
    focus_hwnd: int = 0,
    app_paths: Any = None,
    database: Database | None = None,
    approved: bool = True,
) -> PerceptionObservation:
    """list_open_windows + perceive_desktop 순차 호출 → PerceptionObservation."""
    captured_at = time.monotonic()
    raw: dict[str, Any] = {}

    base_ctx = AutomationToolContext(
        params={},
        approved=approved,
        auto_approve_low_risk=True,
        app_paths=app_paths,
        settings=settings,
        database=database,
        summary="cu_perception",
    )

    win_result = registry.run("list_open_windows", base_ctx)
    raw["list_open_windows"] = _tool_result_payload(win_result)
    if win_result.success:
        open_windows_summary = (win_result.detail or win_result.message or "")[:800]
    else:
        open_windows_summary = win_result.message[:400]

    pd_params: dict[str, Any] = {}
    if focus_hwnd:
        # hwnd→title 매핑은 window_controller 확장 전까지 focus_hint 미사용
        pd_params["prefer_window_only"] = False

    pd_ctx = AutomationToolContext(
        params=pd_params,
        approved=approved,
        auto_approve_low_risk=True,
        app_paths=app_paths,
        settings=settings,
        database=database,
        summary="cu_perception perceive_desktop",
    )
    pd_result = registry.run("perceive_desktop", pd_ctx)
    raw["perceive_desktop"] = _tool_result_payload(pd_result)

    active_window_title = ""
    active_process_name = resolve_active_process_name()
    uia_snapshot_summary = ""
    scene_summary = ""
    perception_source: PerceptionSource = "unknown"

    if pd_result.success:
        meta = _parse_perceive_detail(pd_result.detail or "")
        active_window_title = str(meta.get("active_window") or "").strip()
        src = str(meta.get("perception_source") or "unknown").strip().lower()
        if src in ("uia", "ocr", "vlm", "hybrid"):
            perception_source = src  # type: ignore[assignment]
        summary_text = str(meta.get("summary") or pd_result.message or "")
        uia_snapshot_summary, scene_summary = _split_summary_by_source(
            summary_text,
            perception_source,
        )
        if not active_window_title and pd_result.message:
            # perceive: source | title | summary 형식 폴백
            parts = pd_result.message.split("|", 2)
            if len(parts) >= 2:
                active_window_title = parts[1].strip()[:200]
    else:
        scene_summary = pd_result.message[:400]

    if not active_process_name and active_window_title:
        active_process_name = resolve_active_process_name()

    return PerceptionObservation(
        active_window_title=active_window_title,
        active_process_name=active_process_name,
        open_windows_summary=open_windows_summary,
        uia_snapshot_summary=uia_snapshot_summary,
        scene_summary=scene_summary,
        perception_source=perception_source,
        captured_at=captured_at,
        raw_tool_results=raw,
    )


def perception_to_observation_line(p: PerceptionObservation) -> str:
    """LLM 입력용 perceive 한 줄 (내부 상태는 ctx.last_perception)."""
    active = p.active_window_title[:120]
    scene = (p.scene_summary or p.uia_snapshot_summary)[:400]
    return f"perceive: {p.perception_source} | {active} | {scene}"


def windows_to_observation_line(p: PerceptionObservation) -> str:
    """LLM 입력용 창 목록 한 줄."""
    body = p.open_windows_summary.strip()
    if body:
        return f"windows: {body[:400]}"
    return "windows: (none)"
