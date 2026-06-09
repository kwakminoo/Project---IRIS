"""Windows IME — 라틴 입력 전 영문(알파벳) 모드로 전환."""

from __future__ import annotations

import sys

# IME conversion mode (imm.h)
_IME_CMODE_NATIVE = 0x0001
_IME_CMODE_ALPHANUMERIC = 0x0000


def _foreground_hwnd() -> int:
    if sys.platform != "win32":
        return 0
    try:
        import win32gui  # type: ignore

        return int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        return 0


def set_ime_alphanumeric(hwnd: int | None = None) -> tuple[bool, str]:
    """포커스 창 IME를 영문(알파벳) 입력 모드로 — URL·라틴 typewrite 깨짐 방지."""
    if sys.platform != "win32":
        return False, "non_win32"
    target = hwnd or _foreground_hwnd()
    if target <= 0:
        return False, "no_hwnd"
    try:
        import ctypes

        imm32 = ctypes.windll.imm32
        himc = imm32.ImmGetContext(target)
        if not himc:
            return False, "no_imc"
        try:
            imm32.ImmSetConversionStatus(himc, _IME_CMODE_ALPHANUMERIC, 0)
            return True, "ime_alphanumeric"
        finally:
            imm32.ImmReleaseContext(target, himc)
    except Exception as exc:
        return False, str(exc)


def set_ime_native(hwnd: int | None = None) -> tuple[bool, str]:
    """포커스 창 IME를 한글(네이티브) 모드로."""
    if sys.platform != "win32":
        return False, "non_win32"
    target = hwnd or _foreground_hwnd()
    if target <= 0:
        return False, "no_hwnd"
    try:
        import ctypes

        imm32 = ctypes.windll.imm32
        himc = imm32.ImmGetContext(target)
        if not himc:
            return False, "no_imc"
        try:
            imm32.ImmSetConversionStatus(himc, _IME_CMODE_NATIVE, 0)
            return True, "ime_native"
        finally:
            imm32.ImmReleaseContext(target, himc)
    except Exception as exc:
        return False, str(exc)
