"""LLM Intent Router — Gemma 1회 JSON 분류, 실패 시 규칙 라우터 폴백."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from iris.ai.gemma_client import ChatMessage, GemmaClient, FALLBACK_KO
from iris.ai.response_parser import extract_json_object
from iris.assistant.router_policy import RouteLane, RoutedTurn, is_multi_turn_active, resolve_route_lane
from iris.assistant.tool_layer import is_search_intent
from iris.core.command_router import CommandKind, classify_command
from iris.core.context_manager import DialogueContext

INTENT_ROUTER_SYSTEM = """당신은 Iris Intent Router입니다. 사용자 발화를 분석해 JSON만 출력하세요.

원칙:

Unity, Discord, Excel, 유튜브, 카톡, 메모장 등 임의의 앱·작업도 lane=computer_use.
지원 앱 목록·platform enum으로 제한하지 마세요.
실행 방법(버튼/경로)은 쓰지 마세요. Computer Use가 perceive 후 결정합니다.
slots는 선택 힌트(dict). 비어도 됨. 필수 필드 없음.
순수 인사·잡담 → chat_only
날씨·뉴스·영화·최신 이슈 등 웹 검색 요약 → search
PC 사양만 → fast_tool
작업/게임/창작 모드 진입(바로 실행 금지) → multi_turn
lane 기본값: computer_use (PC에서 뭔가 열·조작·보내·재생)

JSON 스키마: { "lane": "computer_use | chat_only | search | fast_tool | multi_turn", "goal": "실행 가능한 한국어 목표 한 문장 (사용자 원문 반영)", "task_type": "open_app | media_play | send_message | call | file | window | multi_step | unknown", "slots": {}, "risk_hint": "low | medium | high | critical", "needs_user_confirm": false, "clarification": null }

critical(셸·삭제·결제·비밀번호·시스템 설정) → needs_user_confirm=true 다른 텍스트 없이 JSON만.
"""

_LANE_ALIASES: dict[str, RouteLane] = {
    "computer_use": RouteLane.COMPUTER_USE,
    "chat_only": RouteLane.CHAT_ONLY,
    "search": RouteLane.SEARCH,
    "fast_tool": RouteLane.FAST_TOOL,
    "multi_turn": RouteLane.MULTI_TURN,
}


@dataclass
class RoutedIntent:
    """LLM Intent Router 출력."""

    lane: RouteLane
    goal: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    task_type: str | None = None
    risk_hint: str = "low"
    needs_user_confirm: bool = False
    clarification: str | None = None

    def to_routed_turn(self, kind: CommandKind) -> RoutedTurn:
        return RoutedTurn(
            kind=kind,
            lane=self.lane,
            goal=self.goal,
            slots=dict(self.slots),
            task_type=self.task_type,
            risk_hint=self.risk_hint,
            needs_user_confirm=self.needs_user_confirm,
            clarification=self.clarification,
        )


def _is_llm_unavailable(text: str) -> bool:
    return text.strip() == FALLBACK_KO or text.strip().startswith("로컬 언어 모델")


def _parse_lane(raw: object) -> RouteLane | None:
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    return _LANE_ALIASES.get(key)


def _parse_slots(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    return {}


def _kind_for_lane(user_text: str, lane: RouteLane, fallback: CommandKind) -> CommandKind:
    if lane is RouteLane.SEARCH:
        k = classify_command(user_text)
        return k if is_search_intent(k) else CommandKind.WEB_SEARCH
    if lane is RouteLane.FAST_TOOL:
        return CommandKind.GET_SYSTEM_INFO
    if lane is RouteLane.COMPUTER_USE:
        k = classify_command(user_text)
        if k in {CommandKind.COMPUTER_USE, CommandKind.COMPLEX_AUTOMATION}:
            return k
        return CommandKind.COMPUTER_USE
    if lane is RouteLane.MULTI_TURN:
        k = classify_command(user_text)
        if k in {
            CommandKind.WORK_MODE,
            CommandKind.GAME_MODE,
            CommandKind.CREATIVE_MODE,
        }:
            return k
        return fallback
    return fallback


def parse_llm_intent_json(raw: Mapping[str, Any], user_text: str) -> RoutedIntent | None:
    """LLM JSON dict → RoutedIntent. 파싱 불가 시 None."""
    lane = _parse_lane(raw.get("lane"))
    if lane is None:
        return None

    goal_raw = raw.get("goal")
    goal = goal_raw.strip() if isinstance(goal_raw, str) and goal_raw.strip() else user_text.strip()

    task_type = raw.get("task_type")
    task_type_str = task_type.strip() if isinstance(task_type, str) and task_type.strip() else None

    risk = raw.get("risk_hint")
    risk_hint = risk.strip().lower() if isinstance(risk, str) else "low"

    needs = raw.get("needs_user_confirm")
    needs_confirm = bool(needs) if needs is not None else risk_hint == "critical"

    clar = raw.get("clarification")
    clarification = clar.strip() if isinstance(clar, str) and clar.strip() else None

    return RoutedIntent(
        lane=lane,
        goal=goal,
        slots=_parse_slots(raw.get("slots")),
        task_type=task_type_str,
        risk_hint=risk_hint,
        needs_user_confirm=needs_confirm,
        clarification=clarification,
    )


def route_with_llm(
    user_text: str,
    ctx: DialogueContext,
    gemma: GemmaClient,
    *,
    fallback_kind: CommandKind | None = None,
) -> RoutedTurn:
    """Gemma 1회 Intent JSON → RoutedTurn. 실패 시 classify_command + resolve_route_lane."""
    kind = fallback_kind if fallback_kind is not None else classify_command(user_text)

    if is_multi_turn_active(ctx):
        return resolve_route_lane(user_text, kind, ctx)

    messages = [
        ChatMessage(role="system", content=INTENT_ROUTER_SYSTEM),
        ChatMessage(role="user", content=user_text.strip()),
    ]
    raw_reply = gemma.chat(messages)
    if _is_llm_unavailable(raw_reply):
        return resolve_route_lane(user_text, kind, ctx)

    data = extract_json_object(raw_reply)
    if not data:
        return resolve_route_lane(user_text, kind, ctx)

    intent = parse_llm_intent_json(data, user_text)
    if intent is None:
        return resolve_route_lane(user_text, kind, ctx)

    kind = _kind_for_lane(user_text, intent.lane, kind)
    routed = intent.to_routed_turn(kind)

    # LLM이 computer_use면 detect_open_url로 DIRECT_ACTION 덮어쓰기 금지
    if intent.lane is RouteLane.COMPUTER_USE:
        return routed

    return routed
