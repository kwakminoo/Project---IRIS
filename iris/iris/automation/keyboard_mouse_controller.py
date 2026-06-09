"""키보드/마우스 — 승인 후에만 사용."""

from __future__ import annotations


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


def type_text_approved(
    text: str,
    approved: bool,
    *,
    interval: float = 0.03,
    verify_enabled: bool = True,
    max_retries: int = 1,
) -> tuple[bool, str]:
    """승인된 경우에만 입력 — IME·UIA 사전 처리, 검증/재시도 최소."""
    if not approved:
        return False, "승인 필요"
    from iris.automation.text_input_controller import type_text_smart

    outcome = type_text_smart(
        text,
        interval=interval,
        verify_enabled=verify_enabled,
        max_retries=max_retries,
    )
    detail = outcome.message
    if outcome.verified:
        detail = f"{detail}|ok"
    if outcome.retried:
        detail = f"{detail}|retried"
    return outcome.success, f"{outcome.mode}:{detail}"
