"""메시지 앱별 UIA 힌트 — 하드코드 경로 없이 name/automation_id만 사용."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageAppUiaProfile:
    """카톡·디스코드 등 메시지 앱 UIA 선택자."""

    window_title_sub: str
    input_field_name: str | None = None
    input_field_automation_id: str | None = None
    send_button_name: str | None = None
    send_button_automation_id: str | None = None
    send_hotkey: tuple[str, ...] = ("enter",)
    recipient_search_edit_name: str | None = None
    login_ui_markers: tuple[str, ...] = ()


# app_key → UIA 프로필 (app_index 키와 일치)
MESSAGE_APP_UIA: dict[str, MessageAppUiaProfile] = {
    "kakaotalk": MessageAppUiaProfile(
        window_title_sub="카카오톡",
        input_field_name="메시지 입력",
        send_button_name="전송",
        recipient_search_edit_name="검색",
        login_ui_markers=("로그인", "QR", "인증", "2단계"),
    ),
    "discord": MessageAppUiaProfile(
        window_title_sub="Discord",
        input_field_name="Message",
        input_field_automation_id="message-input",
        send_button_name="Send",
        send_hotkey=("enter",),
        login_ui_markers=("Log In", "Login", "Verify", "2FA", "로그인"),
    ),
}


def profile_for_app(app_key: str) -> MessageAppUiaProfile | None:
    """app_key → UIA 프로필 (없으면 None — 범용 focus+type_text 폴백)."""
    key = (app_key or "").strip().lower()
    return MESSAGE_APP_UIA.get(key)
