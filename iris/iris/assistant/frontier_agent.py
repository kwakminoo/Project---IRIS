"""Frontier — 한 번의 LLM 호출로 user_reply + 실행 envelope 수신."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.response_parser import extract_json_object
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.dialogue_agent import build_dialogue_messages
from iris.assistant.router_policy import RouteLane, RoutedTurn, is_multi_turn_active
from iris.assistant.unified_router import (
    _build_dialogue_context_block,
    _is_llm_unavailable,
    envelope_route_to_routed_turn,
)
from iris.config.app_index import resolve_app_candidates_for_llm
from iris.core.activity_sink import push_activity_line
from iris.core.context_manager import DialogueContext

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant


FRONTIER_SYSTEM = """당신은 Iris, Windows 로컬 실행형 AI 비서의 Frontier입니다.
한 번의 JSON으로 (1) 사용자에게 들릴 말 user_reply, (2) 라우팅 route를 출력하세요.

페르소나: 짧고 친절한 한국어. 마크다운·이모지·코드펜스 금지.

=== knowledge_lane (Unified Router와 동일 — 먼저 결정) ===
A) chat_only — 웹 검색·PC 실행 없음
- 인사·감사·잡담·능력 소개·일반 조언(시점·수치 불필요)
- needs_execution=false, route.lane=chat_only, user_reply에 답변 전체
B) search — 웹 검색 후 답변 (시점 민감·사실 질문)
- 날씨·뉴스·영화·주가·환율·정의·비교(vs)·"~가 뭐야"·최신·오늘·지금
- needs_execution=true, route.lane=search, knowledge_lane=search
- slots.query(필수), search_topic(weather|news|movie|general|comparison|definition 등)
- user_reply는 짧은 진행 멘트만 ("확인해볼게요"). 수치·날씨 단정 금지
C) hybrid — 검색+보완
- needs_execution=true, lane=hybrid, knowledge_lane=hybrid

=== PC 실행 (needs_execution=true, user_reply 짧게) ===
- launch_app/direct_action/computer_use/fast_tool/multi_turn — app_catalog만 참고
- 완료 단정("열었습니다" 등) 금지. critical은 needs_user_confirm=true

=== route 필드 ===
intent, lane, knowledge_lane, goal, task_type, slots, risk_hint,
needs_user_confirm, clarification — Unified Router JSON과 동일.

출력(JSON만):
{
  "user_reply": "한국어",
  "needs_execution": false,
  "confidence": 0.0,
  "route": { ... }
}
일관성:
- needs_execution=false → lane은 chat_only 또는 search/hybrid(지식 위임, PC 없음)
- needs_execution=true → lane은 chat_only 금지
- knowledge_lane=search 이면 lane=search, 날씨 등은 search_topic=weather
"""

# 지식 검색 위임 — PC 실행 플래그 없이 허용
_KNOWLEDGE_DELEGATE_LANES = frozenset({RouteLane.SEARCH, RouteLane.HYBRID})


@dataclass
class FrontierResult:
    """Frontier 1회 호출 성공 결과."""

    user_reply: str
    needs_execution: bool
    routed_turn: RoutedTurn
    confidence: float
    logs: list[str] = field(default_factory=list)


def _frontier_min_confidence(assistant: IrisAssistant) -> float:
    settings = assistant._settings
    if settings is None:
        return 0.65
    return float(getattr(settings, "frontier_min_confidence", 0.65))


def _recent_turn_lines(assistant: IrisAssistant) -> list[str]:
    hist = assistant.memory.short_term_history()
    lines: list[str] = []
    for msg in hist[-8:]:
        role = "user" if msg.role == "user" else "assistant"
        body = (msg.content or "").strip()[:120]
        if body:
            lines.append(f"{role}: {body}")
    return lines[-4:]


def _build_frontier_user_block(
    user_text: str,
    ctx: DialogueContext,
    *,
    app_catalog_json: str,
    recent_block: str,
    dialogue_history_block: str,
) -> str:
    hint_line = ""
    hint_raw = ctx.slots.get("last_execution_hint")
    if isinstance(hint_raw, str) and hint_raw.strip():
        hint_line = f"last_execution_hint={hint_raw.strip()[:80]!r}\n"
    return (
        f"user_text={user_text!r}\n"
        f"{_build_dialogue_context_block(ctx)}\n"
        f"{hint_line}"
        f"{dialogue_history_block}\n"
        f"app_catalog={app_catalog_json}\n"
        f"{recent_block}\n"
        "risk_policy: critical 작업은 needs_user_confirm=true"
    )


def _parse_frontier_envelope(
    data: dict[str, Any],
    user_text: str,
    catalog: list[dict[str, str]],
    *,
    min_confidence: float,
) -> FrontierResult | None:
    """Frontier JSON → FrontierResult. 불일치·저신뢰 시 None(폴백)."""
    reply_raw = data.get("user_reply")
    if not isinstance(reply_raw, str) or not reply_raw.strip():
        return None

    needs_raw = data.get("needs_execution")
    if not isinstance(needs_raw, bool):
        return None

    conf_raw = data.get("confidence")
    try:
        confidence = float(conf_raw) if conf_raw is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < min_confidence:
        return None

    route_raw = data.get("route")
    if not isinstance(route_raw, dict):
        return None

    routed = envelope_route_to_routed_turn(route_raw, user_text, catalog)
    if routed is None:
        return None

    # envelope 일관성 — 잘못된 조합은 Unified Router 폴백
    if not needs_raw:
        if routed.lane not in {RouteLane.CHAT_ONLY, *_KNOWLEDGE_DELEGATE_LANES}:
            return None
    elif routed.lane is RouteLane.CHAT_ONLY:
        return None

    return FrontierResult(
        user_reply=reply_raw.strip(),
        needs_execution=needs_raw,
        routed_turn=routed,
        confidence=confidence,
    )


def run_frontier_turn(
    user_text: str,
    ctx: DialogueContext,
    gemma: GemmaClient,
    *,
    assistant: IrisAssistant | None = None,
) -> FrontierResult | None:
    """
    Frontier 1회 LLM — user_reply + route envelope.
    실패·저신뢰·불일치 시 None → TurnCoordinator가 Unified Router 폴백.
    """
    text = user_text.strip()
    if not text or assistant is None:
        return None

    # 멀티턴·pending_cu는 TurnCoordinator가 선처리 — 여기서도 방어
    if is_multi_turn_active(ctx):
        return None

    settings = assistant._settings
    history_turns = 4
    if settings is not None:
        history_turns = max(0, int(getattr(settings, "dialogue_history_turns", 4)))

    hist = list(assistant.memory.short_term_history())
    dialogue_msgs = build_dialogue_messages(
        text,
        history=hist,
        max_history_turns=history_turns,
    )
    dialogue_lines = []
    for msg in dialogue_msgs:
        if msg.role == "system":
            continue
        role = "user" if msg.role == "user" else "assistant"
        dialogue_lines.append(f"{role}: {msg.content.strip()[:200]}")
    dialogue_history_block = "dialogue_context=\n" + "\n".join(dialogue_lines[-(history_turns * 2) :])

    catalog = resolve_app_candidates_for_llm(
        text,
        assistant._app_paths,
        db=assistant._db,
        top_k=8,
    )
    catalog_json = json.dumps(catalog or [], ensure_ascii=False)
    recent_block = ""
    recent = _recent_turn_lines(assistant)
    if recent:
        recent_block = "recent_turns=" + json.dumps(recent, ensure_ascii=False)

    user_block = _build_frontier_user_block(
        text,
        ctx,
        app_catalog_json=catalog_json,
        recent_block=recent_block,
        dialogue_history_block=dialogue_history_block,
    )

    messages = [
        ChatMessage(role="system", content=FRONTIER_SYSTEM),
        ChatMessage(role="user", content=user_block),
    ]
    push_activity_line("Frontier: single LLM envelope call.")
    raw_reply = gemma.chat(messages, purpose=LlmPurpose.FRONTIER)
    logs = ["frontier_call"]

    if _is_llm_unavailable(raw_reply):
        push_activity_line("Frontier: LLM offline — fallback to unified router.")
        logs.append("frontier_offline")
        return None

    data = extract_json_object(raw_reply)
    if not data:
        push_activity_line("Frontier: JSON extract failed — fallback.")
        logs.append("frontier_json_fail")
        return None

    min_conf = _frontier_min_confidence(assistant)
    parsed = _parse_frontier_envelope(
        data,
        text,
        catalog or [],
        min_confidence=min_conf,
    )
    if parsed is None:
        push_activity_line("Frontier: envelope invalid or low confidence — fallback.")
        logs.append("frontier_invalid")
        return None

    parsed.logs = logs + [
        f"frontier_confidence={parsed.confidence:.2f}",
        f"needs_execution={parsed.needs_execution}",
        f"lane={parsed.routed_turn.lane.value}",
    ]
    push_activity_line(
        f"Frontier: ok needs_execution={parsed.needs_execution} "
        f"lane={parsed.routed_turn.lane.value}."
    )
    return parsed
