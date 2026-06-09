"""도구 실행·승인·early_ack 사용자 멘트 — Registry preview/result 기반 (regex 마스킹 없음)."""

from __future__ import annotations

from typing import Any, Mapping

from iris.automation.tool_types import AutomationToolResult

# 승인·완료 멘트에 그대로 노출해도 되는 preview 접두사
_PREVIEW_PREFIX = "- "


def _strip_or_empty(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def format_action_preview_line(
    tool: str,
    preview: str,
    params: Mapping[str, Any] | None = None,
) -> str:
    """
    승인 UI용 action 한 줄 — AutomationToolRegistry.preview() 결과를 우선 사용.
    preview가 비어 있으면 도구·params로 최소 설명만 구성.
    """
    _ = params  # 호출부 호환; factual 멘트는 preview가 정본
    shown = _strip_or_empty(preview)
    if shown:
        return f"{_PREVIEW_PREFIX}{shown}"
    tool_name = _strip_or_empty(tool) or "작업"
    return f"{_PREVIEW_PREFIX}{tool_name}"


def format_user_approval_message(
    tool: str,
    preview: str,
    params: dict[str, Any] | None = None,
) -> str:
    """CRITICAL 도구 승인 요청 — preview 원문을 사용자에게 표시."""
    action = format_action_preview_line(tool, preview, params or {})
    body = action.removeprefix(_PREVIEW_PREFIX).strip()
    return f"이 작업을 진행하려면 확인이 필요합니다. 진행할까요?\n- {body}"


def format_pending_tool_user_message(
    tool_name: str,
    result: AutomationToolResult,
    display_hint: str = "",
) -> str:
    """승인 후 1스텝 또는 quick path 실행 결과 — result.message/detail을 그대로 반영."""
    if not result.success:
        reason = _strip_or_empty(result.message) or "실행에 실패했습니다."
        return f"요청하신 작업을 실행하지 못했습니다. {reason}"

    primary = _strip_or_empty(result.message)
    if not primary and display_hint:
        primary = display_hint.strip()
    if not primary:
        primary = "완료했습니다."

    detail = _strip_or_empty(result.detail)
    if detail and detail not in primary:
        # 짧은 보조 정보만 덧붙임 (긴 JSON·로그는 message만)
        if len(detail) <= 160:
            return f"{primary} ({detail})"
    return primary


def format_cu_early_ack(goal: str, slots: Mapping[str, Any] | None = None) -> str:
    """
    Computer Use 실행 전 짧은 안내 — Router slots·구조 필드 기반 (goal 원문 echo 금지).
    regex 앱 이름 매칭(_ACK_TEMPLATES) 대신 slots만 사용.
    """
    slot = dict(slots) if slots else {}
    g = _strip_or_empty(goal)

    disp = _strip_or_empty(slot.get("display_name"))
    if disp:
        return f"{disp} 관련 작업을 진행할게요."

    media_action = _strip_or_empty(slot.get("media_action")).lower()
    if media_action in {"search", "play"}:
        sq_raw = slot.get("search_query") or slot.get("query") or slot.get("title")
        q = _strip_or_empty(sq_raw)[:40] if sq_raw else ""
        sc = _strip_or_empty(slot.get("success_criteria")).lower()
        if sc in {"", "search_results_visible"} and media_action == "search":
            if q:
                return f"'{q}' 검색 결과를 열게요."
            return "검색 결과를 열게요."
        if sc in {"", "playback_confirmed", "play_confirmed"} or media_action == "play":
            if q:
                return f"'{q}' 찾아서 재생을 시도할게요."
            return "찾아서 재생을 시도할게요."

    task_type = _strip_or_empty(slot.get("task_type")).lower()
    text_body = _strip_or_empty(slot.get("text_to_type") or slot.get("message_text"))
    app_label = _strip_or_empty(slot.get("app_key")) or "앱"

    if task_type == "compose_text" and text_body:
        snippet = text_body[:30] + ("…" if len(text_body) > 30 else "")
        return f"{app_label}에 '{snippet}'을(를) 입력할게요."
    if task_type == "send_message" and text_body:
        snippet = text_body[:30] + ("…" if len(text_body) > 30 else "")
        return f"{app_label}에 '{snippet}' 메시지를 보낼게요."
    if task_type == "send_message":
        return f"{app_label}에 메시지를 보낼게요."
    if task_type == "open_app" and disp:
        return f"{disp}을(를) 실행할게요."

    summary = _strip_or_empty(slot.get("user_request_summary"))
    if summary and summary != g:
        return f"{summary[:60]} 작업을 진행할게요."

    return "요청하신 작업을 진행할게요."
