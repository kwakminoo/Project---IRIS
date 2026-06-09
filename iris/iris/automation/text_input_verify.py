"""type_text 결과 검증 — typewrite·unicode 경로만 최소 검증."""

from __future__ import annotations

import re
import unicodedata

_HANGUL_RE = re.compile(r"[가-힣]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# UIA 직접 주입은 신뢰 — 검증 생략
_TRUSTED_MODES = frozenset({"uia_set_text", "uia_value", "uia_type_keys"})


def script_kind(text: str) -> str:
    """latin | hangul | mixed | empty."""
    t = (text or "").strip()
    if not t:
        return "empty"
    has_h = bool(_HANGUL_RE.search(t))
    has_l = bool(_LATIN_RE.search(t))
    if has_h and has_l:
        return "mixed"
    if has_h:
        return "hangul"
    return "latin"


def should_verify_after_mode(mode: str, *, verify_enabled: bool) -> bool:
    """검증·재시도 최소화 — UIA 성공 경로는 검증 생략."""
    if not verify_enabled:
        return False
    return mode not in _TRUSTED_MODES


def normalize_for_compare(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "").strip().lower())


def text_matches_expected(expected: str, actual: str) -> bool:
    """느슨한 일치 — 전체·핵심 부분 문자열."""
    exp = normalize_for_compare(expected)
    act = normalize_for_compare(actual)
    if not exp:
        return True
    if not act:
        return False
    if exp == act or exp in act or act in exp:
        return True
    # URL: 스킴·호스트만 비교
    if "://" in exp:
        host = exp.split("://", 1)[-1].split("/")[0].split("?")[0]
        if host and host in act:
            return True
    # 한글: 앞 4자 이상 포함
    if _HANGUL_RE.search(exp):
        chunk = exp[: max(4, min(len(exp), 12))]
        return chunk in act
    # 라틴: 알파벳·숫자만 추출해 포함 여부
    exp_alnum = re.sub(r"[^a-z0-9]", "", exp)
    act_alnum = re.sub(r"[^a-z0-9]", "", act)
    if len(exp_alnum) >= 4 and exp_alnum in act_alnum:
        return True
    return False


def read_focused_field_text() -> tuple[bool, str]:
    """포커스 창 UIA Document/Edit 값 읽기."""
    try:
        import win32gui  # type: ignore
        from pywinauto import Desktop  # type: ignore
    except ImportError:
        return False, ""

    try:
        hwnd = int(win32gui.GetForegroundWindow() or 0)
        if hwnd <= 0:
            return False, ""
        desk = Desktop(backend="uia")
        win = desk.window(handle=hwnd)
        for ctrl_type in ("Document", "Edit"):
            try:
                ctrl = win.child_window(control_type=ctrl_type)
                if not ctrl.exists(timeout=0.15):
                    continue
                wrapper = ctrl.wrapper_object()
                for getter in (
                    lambda w: w.window_text(),
                    lambda w: w.get_value() if hasattr(w, "get_value") else "",
                ):
                    try:
                        raw = getter(wrapper)
                        tx = str(raw or "").strip()
                        if tx:
                            return True, tx
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return False, ""
