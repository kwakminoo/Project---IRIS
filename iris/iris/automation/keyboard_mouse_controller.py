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


def type_text_approved(text: str, approved: bool) -> tuple[bool, str]:
    """승인된 경우에만 입력 (최소 구현)."""
    if not approved:
        return False, "승인 필요"
    try:
        import pyautogui  # type: ignore

        pyautogui.typewrite(text, interval=0.01)
        return True, "ok"
    except Exception as e:
        return False, str(e)
