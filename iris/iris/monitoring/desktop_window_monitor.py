"""데스크톱 창 텍스트: UIA 우선, 실패 시 창 영역 OCR."""

from __future__ import annotations

import json

from iris.automation import uia_reader, window_controller
from iris.config.settings import Settings
from iris.monitoring import ocr_engine, screen_capture


def _uia_json_to_plain(json_text: str) -> str:
    """모니터링 스니펫 호환: UIA JSON에서 name 줄만 추출."""
    try:
        data = json.loads(json_text)
        lines = [
            str(e.get("name", "")).strip()
            for e in (data.get("elements") or [])
            if isinstance(e, dict) and str(e.get("name", "")).strip()
        ]
        if lines:
            return "\n".join(lines)[:12000]
    except Exception:
        pass
    return json_text[:12000]


def collect_window_text(settings: Settings, title_sub: str, _process_hint: str = "") -> str:
    """
    pygetwindow으로 창 위치 찾은 뒤 UIA 시도 → OCR 폴백.
    process_hint: 프로세스명 일부 (선택, 향후 확장).
    """
    wins = window_controller.find_windows_by_title_substring(title_sub)
    if not wins:
        return ""

    _, json_text, _ = uia_reader.snapshot_window_uia(title_sub)
    if json_text:
        return _uia_json_to_plain(json_text)

    w0 = wins[0]
    cap = screen_capture.capture_region(int(w0.left), int(w0.top), int(w0.width), int(w0.height))
    if cap:
        raw = ocr_engine.ocr_image(settings, cap)
        summary, _h = ocr_engine.ocr_for_storage(settings, raw)
        return summary or raw[:2000]
    return ""


def collect_for_target_row(
    settings: Settings,
    title: str,
    process_name: str,
) -> str:
    """DB targets 한 행에 대한 스니펫."""
    hint = title or process_name
    return collect_window_text(settings, hint, process_name)
