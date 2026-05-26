"""Computer Use 플래너용 창 스크린샷 (메모리만, SQLite·디스크 저장 없음)."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from iris.automation import window_controller
from iris.monitoring import screen_capture

if TYPE_CHECKING:
    from iris.assistant.computer_use_agent import ComputerUseContext

_MAX_PLANNER_WIDTH = 1280
_SLOT_HINT_KEYS = ("focus_hint", "title_hint", "title_sub", "window_title_sub", "app_hint")


def _hint_from_slots(slots: dict[str, Any]) -> str:
    for key in _SLOT_HINT_KEYS:
        v = str(slots.get(key) or "").strip()
        if v:
            return v
    return ""


def resolve_planner_hwnd(ctx: ComputerUseContext) -> tuple[int, str]:
    """플래너 캡처 대상 HWND — last focus → slots hint → 활성 창."""
    if ctx.last_focus_hwnd > 0:
        return ctx.last_focus_hwnd, "last_focus"
    hint = _hint_from_slots(ctx.slots)
    if hint:
        wins = window_controller.find_windows_by_title_substring(hint)
        if wins and wins[0].hwnd > 0:
            return wins[0].hwnd, "slots_hint"
    active = window_controller.get_active_window_title()
    if active.strip():
        wins = window_controller.find_windows_by_title_substring(active.strip()[:120])
        if wins and wins[0].hwnd > 0:
            return wins[0].hwnd, "active_window"
    return 0, "no_hwnd"


def _encode_planner_png(rgb_bytes: bytes, width: int, height: int) -> tuple[bytes | None, str]:
    """max width 1280 리사이즈 후 PNG (LLM 1장 전송용)."""
    try:
        from PIL import Image  # type: ignore

        img = Image.frombytes("RGB", (width, height), rgb_bytes)
        if img.width > _MAX_PLANNER_WIDTH:
            ratio = _MAX_PLANNER_WIDTH / float(img.width)
            new_h = max(1, int(img.height * ratio))
            img = img.resize((_MAX_PLANNER_WIDTH, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), f"{img.width}x{img.height}"
    except Exception:
        return None, "encode_fail"


def capture_planner_screenshot(ctx: ComputerUseContext) -> tuple[bytes | None, str]:
    """활성/목표 창 PNG 1장 — 실패 시 (None, reason)."""
    hwnd, reason = resolve_planner_hwnd(ctx)
    if hwnd <= 0:
        return None, reason
    cap = screen_capture.capture_window_by_hwnd(hwnd)
    if cap is None:
        return None, f"capture_fail:{reason}"
    png, size_tag = _encode_planner_png(cap.rgb_bytes, cap.width, cap.height)
    if not png:
        return None, f"encode_fail:{reason}"
    return png, f"{size_tag} via {reason}"
