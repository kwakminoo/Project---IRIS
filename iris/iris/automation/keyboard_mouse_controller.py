"""키보드/마우스 — 승인 후에만 사용."""

from __future__ import annotations

import re

# 한글 IME 활성 시 pyautogui.typewrite는 라틴 키가 한글로 변환됨
_HANGUL_RE = re.compile(r"[가-힣]")
_URL_LIKE_RE = re.compile(r"^https?://", re.I)


def send_hotkey_approved(keys: list[str], approved: bool) -> tuple[bool, str]:
    """승인된 경우에만 단축키 조합 (예: ctrl+f)."""
    if not approved:
        return False, "승인 필요"
    if not keys:
        return False, "keys가 비어 있습니다."
    try:
        import pyautogui  # type: ignore

        pyautogui.hotkey(*[str(k).strip() for k in keys if str(k).strip()])
        return True, "+".join(str(k) for k in keys)
    except Exception as e:
        return False, str(e)


def _should_paste_instead_of_typewrite(text: str) -> bool:
    """URL·ASCII 텍스트는 IME 영향 없는 붙여넣기 경로를 사용."""
    t = (text or "").strip()
    if not t:
        return False
    if _URL_LIKE_RE.match(t) or "://" in t:
        return True
    # 한글이 없는 라틴/기호 문자열 — 주소창 URL 등
    return _HANGUL_RE.search(t) is None


def _clipboard_get_text() -> str:
    import win32clipboard  # type: ignore

    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return str(data) if data is not None else ""
    finally:
        win32clipboard.CloseClipboard()
    return ""


def _clipboard_set_text(text: str) -> None:
    import win32clipboard  # type: ignore

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def paste_text_approved(text: str, approved: bool) -> tuple[bool, str]:
    """클립보드 붙여넣기 — IME 상태와 무관하게 정확한 문자열 입력."""
    if not approved:
        return False, "승인 필요"
    payload = str(text or "")
    if not payload:
        return False, "text가 비어 있습니다."
    try:
        import pyautogui  # type: ignore

        previous = ""
        try:
            previous = _clipboard_get_text()
        except Exception:
            previous = ""
        try:
            _clipboard_set_text(payload)
            pyautogui.hotkey("ctrl", "v")
        finally:
            try:
                _clipboard_set_text(previous)
            except Exception:
                pass
        return True, "paste"
    except Exception as e:
        return False, str(e)


def type_text_approved(text: str, approved: bool) -> tuple[bool, str]:
    """승인된 경우에만 입력."""
    if not approved:
        return False, "승인 필요"
    payload = str(text or "")
    if not payload:
        return False, "text가 비어 있습니다."
    # YouTube watch URL 등 — 한글 IME가 켜져 있어도 정확히 입력
    if _should_paste_instead_of_typewrite(payload):
        return paste_text_approved(payload, approved=True)
    try:
        import pyautogui  # type: ignore

        pyautogui.typewrite(payload, interval=0.01)
        return True, "typewrite"
    except Exception as e:
        return False, str(e)
