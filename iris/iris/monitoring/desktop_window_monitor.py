"""데스크톱 창 텍스트: UIA 우선, 실패 시 창 영역 OCR."""

from __future__ import annotations

from typing import List

from iris.automation import window_controller
from iris.config.settings import Settings
from iris.monitoring import ocr_engine, screen_capture


def collect_window_text(settings: Settings, title_sub: str, _process_hint: str = "") -> str:
    """
    pygetwindow으로 창 위치 찾은 뒤 UIA 시도 → OCR 폴백.
    process_hint: 프로세스명 일부 (선택).
    """
    wins = window_controller.find_windows_by_title_substring(title_sub)
    if not wins:
        return ""
    w0 = wins[0]
    # UIA 시도
    try:
        from pywinauto import Desktop  # type: ignore

        desk = Desktop(backend="uia")
        for win in desk.windows():
            try:
                t = win.window_text() or ""
            except Exception:
                continue
            if title_sub.lower() in t.lower():
                texts: List[str] = []
                try:
                    for c in win.descendants():
                        try:
                            tx = c.window_text()
                            if tx and len(tx.strip()) > 1:
                                texts.append(tx.strip())
                        except Exception:
                            continue
                except Exception:
                    pass
                if texts:
                    return "\n".join(texts[:200])[:12000]
    except Exception:
        pass

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
