"""Unified Router — compose_text / send_message 슬롯 검증."""

from __future__ import annotations

from iris.assistant.router_policy import RouteLane
from iris.assistant.unified_router import _payload_to_routed_turn, parse_unified_route_json
from iris.core.command_router import CommandKind


def test_router_clarify_compose_text_missing_text() -> None:
    payload = parse_unified_route_json(
        {
            "intent": "computer_use",
            "lane": "computer_use",
            "goal": "메모장에 적어줘",
            "task_type": "compose_text",
            "slots": {"app_key": "notepad"},
            "risk_hint": "low",
            "needs_user_confirm": False,
            "confidence": 0.9,
        },
        "메모장에 적어줘",
    )
    assert payload is not None
    routed = _payload_to_routed_turn(
        payload, "메모장에 적어줘", [], fallback_kind=CommandKind.GENERAL_CHAT
    )
    assert routed.lane is RouteLane.CHAT_ONLY
    assert routed.clarification == "어떤 내용을 입력할까요?"


def test_router_clarify_send_message_missing_text() -> None:
    payload = parse_unified_route_json(
        {
            "intent": "computer_use",
            "lane": "computer_use",
            "goal": "디스코드에 보내",
            "task_type": "send_message",
            "slots": {"app_key": "discord"},
            "risk_hint": "low",
            "needs_user_confirm": False,
            "confidence": 0.9,
        },
        "디스코드에 보내",
    )
    assert payload is not None
    routed = _payload_to_routed_turn(
        payload, "디스코드에 보내", [], fallback_kind=CommandKind.GENERAL_CHAT
    )
    assert routed.lane is RouteLane.CHAT_ONLY
    assert "보낼까요" in (routed.clarification or "")


def test_router_compose_text_complete_slots_goes_cu() -> None:
    payload = parse_unified_route_json(
        {
            "intent": "computer_use",
            "lane": "computer_use",
            "goal": "메모장 hello",
            "task_type": "compose_text",
            "slots": {"app_key": "notepad", "text_to_type": "hello"},
            "risk_hint": "low",
            "needs_user_confirm": False,
            "confidence": 0.9,
        },
        "메모장 hello",
    )
    assert payload is not None
    routed = _payload_to_routed_turn(
        payload, "메모장 hello", [], fallback_kind=CommandKind.GENERAL_CHAT
    )
    assert routed.lane is RouteLane.COMPUTER_USE
    assert routed.kind is CommandKind.COMPUTER_USE
