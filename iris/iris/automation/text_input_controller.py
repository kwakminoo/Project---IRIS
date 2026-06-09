"""스마트 텍스트 입력 — IME·UIA 사전 처리로 검증/재시도 최소화."""

from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from typing import Literal

from iris.automation import ime_control
from iris.automation.text_input_verify import (
    read_focused_field_text,
    script_kind,
    should_verify_after_mode,
    text_matches_expected,
)

InputMode = Literal[
    "uia_set_text",
    "uia_value",
    "uia_type_keys",
    "typewrite",
    "unicode",
    "failed",
]


@dataclass(frozen=True)
class TypeTextOutcome:
    success: bool
    mode: InputMode
    message: str
    verified: bool = False
    retried: bool = False


def _clear_focused_field() -> None:
    try:
        import pyautogui  # type: ignore

        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.press("backspace")
        time.sleep(0.05)
    except Exception:
        pass


def _try_uia_set_text(text: str) -> tuple[bool, InputMode, str]:
    """활성 창 Document/Edit에 값 직접 설정 — IME 영향 없음."""
    try:
        import win32gui  # type: ignore
        from pywinauto import Desktop  # type: ignore
    except ImportError:
        return False, "failed", "pywinauto_missing"

    try:
        hwnd = int(win32gui.GetForegroundWindow() or 0)
        if hwnd <= 0:
            return False, "failed", "no_hwnd"
        desk = Desktop(backend="uia")
        win = desk.window(handle=hwnd)
        for ctrl_type in ("Document", "Edit"):
            try:
                ctrl = win.child_window(control_type=ctrl_type)
                if not ctrl.exists(timeout=0.2):
                    continue
                ctrl.set_focus()
                wrapper = ctrl.wrapper_object()
                if hasattr(wrapper, "set_text"):
                    wrapper.set_text(text)
                    return True, "uia_set_text", "uia_set_text"
                if hasattr(wrapper, "iface_value"):
                    wrapper.iface_value.SetValue(text)  # type: ignore[attr-defined]
                    return True, "uia_value", "uia_value"
            except Exception:
                continue
    except Exception as exc:
        return False, "failed", str(exc)
    return False, "failed", "uia_miss"


def _typewrite_latin(text: str, interval: float) -> tuple[bool, str]:
    ime_control.set_ime_alphanumeric()
    time.sleep(0.06)
    try:
        import pyautogui  # type: ignore

        pyautogui.typewrite(text, interval=max(0.02, interval))
        return True, "typewrite"
    except Exception as exc:
        return False, str(exc)


def _send_unicode_visible(text: str, interval: float) -> tuple[bool, str]:
    """한글 등 — Unicode SendInput, 글자 간격으로 타이핑처럼 보이게."""
    if not text:
        return False, "empty"
    try:
        import win32gui  # type: ignore

        hwnd = int(win32gui.GetForegroundWindow() or 0)
        if script_kind(text) in ("hangul", "mixed"):
            ime_control.set_ime_native(hwnd or None)
            time.sleep(0.05)
    except Exception:
        pass

    try:
        for ch in text:
            _send_unicode_char(ord(ch))
            time.sleep(max(0.02, interval))
        return True, "unicode"
    except Exception as exc:
        return False, str(exc)


def _send_unicode_char(code: int) -> None:
    import ctypes.wintypes as wt

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wt.WORD),
            ("wScan", wt.WORD),
            ("dwFlags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        _anonymous_ = ("i",)
        _fields_ = [("type", wt.DWORD), ("i", _I)]

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    inp_down = INPUT(type=1, ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0))
    inp_up = INPUT(
        type=1,
        ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0),
    )
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))


def _attempt_type(
    text: str,
    *,
    interval: float,
    force_uia: bool,
) -> tuple[bool, InputMode, str]:
    kind = script_kind(text)
    if force_uia or kind in ("hangul", "mixed"):
        ok, mode, detail = _try_uia_set_text(text)
        if ok:
            return True, mode, detail
    if kind == "latin":
        ok, detail = _typewrite_latin(text, interval)
        return ok, "typewrite" if ok else "failed", detail
    ok, detail = _send_unicode_visible(text, interval)
    return ok, "unicode" if ok else "failed", detail


def type_text_smart(
    text: str,
    *,
    interval: float = 0.03,
    verify_enabled: bool = True,
    max_retries: int = 1,
) -> TypeTextOutcome:
    """
    스마트 입력 + 최소 검증/재시도.
    - 한글·혼합: UIA 직접 설정 우선 (검증 생략)
    - 라틴: IME 영문 후 typewrite, 불일치 시 1회만 UIA 재시도
    """
    payload = str(text or "")
    if not payload:
        return TypeTextOutcome(False, "failed", "text가 비어 있습니다.")

    retries = max(0, min(int(max_retries), 1))
    ok, mode, detail = _attempt_type(payload, interval=interval, force_uia=False)
    if not ok:
        return TypeTextOutcome(False, "failed", detail or "입력 실패")

    if not should_verify_after_mode(mode, verify_enabled=verify_enabled):
        return TypeTextOutcome(True, mode, detail, verified=False)

    time.sleep(0.12)
    _read_ok, actual = read_focused_field_text()
    if not _read_ok:
        # 읽기 실패 시 재시도 없이 성공 처리 — 불필요한 재시도 방지
        return TypeTextOutcome(True, mode, f"{detail}|verify_skipped_no_read")

    if text_matches_expected(payload, actual):
        return TypeTextOutcome(True, mode, f"{detail}|verified", verified=True)

    if retries < 1:
        return TypeTextOutcome(
            False,
            mode,
            f"{detail}|verify_mismatch",
            verified=False,
        )

    _clear_focused_field()
    time.sleep(0.08)
    ok2, mode2, detail2 = _attempt_type(payload, interval=interval, force_uia=True)
    if not ok2:
        return TypeTextOutcome(False, "failed", detail2 or "retry_failed", retried=True)

    if not should_verify_after_mode(mode2, verify_enabled=verify_enabled):
        return TypeTextOutcome(True, mode2, detail2, retried=True)

    time.sleep(0.12)
    _read_ok2, actual2 = read_focused_field_text()
    if _read_ok2 and text_matches_expected(payload, actual2):
        return TypeTextOutcome(True, mode2, f"{detail2}|verified_retry", verified=True, retried=True)

    return TypeTextOutcome(
        False,
        mode2,
        f"{detail2}|verify_mismatch_after_retry",
        verified=False,
        retried=True,
    )


# 스펙·Flow 호출 호환 alias
smart_type_text = type_text_smart
