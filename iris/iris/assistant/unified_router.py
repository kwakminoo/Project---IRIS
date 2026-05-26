"""Unified LLM Router — 자연어 전체를 Gemma JSON으로 해석해 lane·intent·slots 결정."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, TYPE_CHECKING

from iris.ai.gemma_client import ChatMessage, GemmaClient, FALLBACK_KO
from iris.ai.thinking_policy import LlmPurpose
from iris.ai.response_parser import extract_json_object
from iris.assistant.router_policy import (
    RouteLane,
    RoutedTurn,
    detect_open_url,
    is_multi_turn_active,
    resolve_route_lane,
)
from iris.assistant.tool_layer import is_search_intent
from iris.config.app_index import resolve_app_candidates_for_llm
from iris.core.activity_sink import push_activity_line
from iris.core.command_router import CommandKind, legacy_classify_command
from iris.assistant.media_completion import normalize_routed_media_slots
from iris.core.context_manager import DialogueContext

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant

UNIFIED_ROUTER_SYSTEM = """당신은 Iris Unified Router입니다. 사용자 발화를 분석해 JSON만 출력하세요.

역할: 무엇을 원하는지(intent)와 어떻게 실행할지(lane·slots)를 결정합니다. 실행 방법·버튼 경로는 쓰지 마세요.

라우팅 규칙:
- 로컬 PC 앱 실행(스팀, 메모장, 디스코드 등 + 켜줘/실행/열어/해달라/부탁 등 모든 구어) → intent=launch_app, lane=direct_action, slots.app_key는 app_catalog에 있는 키만. catalog에 없으면 intent=computer_use, search 금지.
- 웹 정보·날씨·뉴스·영화·"~가 뭐야" 조사 → intent=search, lane=search, slots.query에 실제 검색에 쓸 짧은 질의 한 줄(필수). PC 앱 실행과 혼동 금지.
- 멀티 스텝 PC 조작(열고 보내고, 메시지 보내기 등) → intent=computer_use, lane=computer_use.
- 미디어(유튜브·스포티파이·넷플릭스 등 검색/재생) → intent=computer_use, lane=computer_use, task_type=media_play, slots에 platform_hint·media_action·search_query 필수 채움(아래 미디어 규칙).
- 순수 인사·잡담 → intent=chat, lane=chat_only.
- PC 사양만 → intent=fast_tool, lane=fast_tool.
- 작업/게임/창작 모드 진입(바로 앱 실행 금지) → intent=work_mode|game_mode|creative_mode, lane=multi_turn.
- 명시 https URL 열기 → slots.url, lane=direct_action 가능.
- critical(셸·삭제·결제·비밀번호·시스템 설정) → risk_hint=critical, needs_user_confirm=true.

pending_cu가 있으면 사용자 답을 approve_followup|reject_followup|clarify|unrelated 중 하나로 분류.

미디어 슬롯 (의도·검색/재생·검색어는 반드시 LLM이 판단 — 규칙 엔진·키워드 매칭 없음):
- task_type=media_play, intent=computer_use, lane=computer_use.
- slots.platform_hint: youtube | spotify | netflix | browser | unknown (불명확하면 unknown).
- slots.media_action:
  - search: 찾아줘·검색해줘·뭐 있어·목록만 → 검색 결과 페이지까지가 목표.
  - play: 틀어줘·재생·들려줘·노래/영상 틀어 → 실제 재생(시청/재생 UI)까지가 목표.
- slots.search_query: 곡명·영상명·채널명·키워드·짧은 구문만. "유튜브에서", "틀어줘", "검색해줘" 등 동사·플랫폼 접두어 제외. STT 오타·표기(예: 치챗/칈챗)는 사용자가 말한 그대로(자동 교정 금지).
- search_query가 비면 needs_user_confirm=true 또는 clarification에 무엇을 찾/틀지 질문, goal에도 질문 포함.
- slots.success_criteria (선택): search → search_results_visible, play → playback_confirmed. URL만 열기는 play/search 완료가 아님.
- slots.skill_id: media_action+search_query가 있으면 media_play (선택, 없으면 코드가 유도).
- slots.user_request_summary: 사용자 원문 요약(선택).
- 재생(play)이면 goal에 "…을 재생한다"까지 명시.

JSON 스키마(엄격):
{
  "intent": "chat|search|launch_app|computer_use|fast_tool|work_mode|game_mode|creative_mode|monitoring|approve_followup|reject_followup|clarify|unrelated",
  "lane": "chat_only|search|direct_action|computer_use|fast_tool|multi_turn",
  "goal": "한국어 실행 목표 한 문장 (재생이면 '…을 재생한다'까지)",
  "task_type": "open_app|media_play|send_message|file|window|multi_step|unknown",
  "slots": {
    "app_key": "",
    "display_name": "",
    "query": "",
    "url": "",
    "platform_hint": "youtube|spotify|netflix|browser|unknown",
    "media_action": "search|play",
    "search_query": "",
    "success_criteria": "search_results_visible|playback_confirmed",
    "skill_id": "media_play",
    "user_request_summary": ""
  },
  "risk_hint": "low|medium|high|critical",
  "needs_user_confirm": false,
  "clarification": null,
  "confidence": 0.0
}

다른 텍스트 없이 JSON만 출력하세요.
"""

_LANE_MAP: dict[str, RouteLane] = {
    "chat_only": RouteLane.CHAT_ONLY,
    "search": RouteLane.SEARCH,
    "direct_action": RouteLane.DIRECT_ACTION,
    "computer_use": RouteLane.COMPUTER_USE,
    "fast_tool": RouteLane.FAST_TOOL,
    "multi_turn": RouteLane.MULTI_TURN,
}

def _normalize_media_slots(slots: dict[str, Any]) -> dict[str, Any]:
    """LLM slots 미디어 필드 정규화 — media_completion.normalize_routed_media_slots 위임."""
    return normalize_routed_media_slots(slots)


_INTENT_MODE_KIND: dict[str, CommandKind] = {
    "work_mode": CommandKind.WORK_MODE,
    "game_mode": CommandKind.GAME_MODE,
    "creative_mode": CommandKind.CREATIVE_MODE,
}


@dataclass
class UnifiedRoutePayload:
    """LLM Unified Router 파싱 결과."""

    intent: str
    lane: RouteLane
    goal: str | None = None
    task_type: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    risk_hint: str = "low"
    needs_user_confirm: bool = False
    clarification: str | None = None
    confidence: float = 0.0


def _is_llm_unavailable(text: str) -> bool:
    return text.strip() == FALLBACK_KO or text.strip().startswith("로컬 언어 모델")


def _parse_lane(raw: object) -> RouteLane | None:
    if not isinstance(raw, str):
        return None
    return _LANE_MAP.get(raw.strip().lower())


def _parse_slots(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if v is not None and str(v).strip() != ""}


def _pick_catalog_entry(
    app_key: str,
    catalog: list[dict[str, str]],
) -> dict[str, str] | None:
    key = app_key.strip().lower()
    for entry in catalog:
        if str(entry.get("app_key", "")).strip().lower() == key:
            return entry
    return None


def _kind_for_search(user_text: str, fallback: CommandKind) -> CommandKind:
    k = legacy_classify_command(user_text)
    return k if is_search_intent(k) else CommandKind.WEB_SEARCH


def _kind_from_payload(
    payload: UnifiedRoutePayload,
    user_text: str,
    *,
    fallback: CommandKind,
) -> CommandKind:
    intent = payload.intent.strip().lower()
    if intent in _INTENT_MODE_KIND:
        return _INTENT_MODE_KIND[intent]
    if intent == "launch_app" or payload.task_type == "open_app":
        return CommandKind.APP_LAUNCH
    if intent == "fast_tool" or payload.lane is RouteLane.FAST_TOOL:
        return CommandKind.GET_SYSTEM_INFO
    if intent == "search" or payload.lane is RouteLane.SEARCH:
        return _kind_for_search(user_text, fallback)
    if intent == "monitoring":
        return CommandKind.MONITORING_STATUS
    if intent in {"computer_use", "approve_followup", "reject_followup", "clarify"}:
        k = legacy_classify_command(user_text)
        if k in {CommandKind.COMPUTER_USE, CommandKind.COMPLEX_AUTOMATION}:
            return k
        return CommandKind.COMPUTER_USE
    if intent == "chat" or payload.lane is RouteLane.CHAT_ONLY:
        return CommandKind.GENERAL_CHAT
    return fallback


def parse_unified_route_json(
    raw: Mapping[str, Any],
    user_text: str,
) -> UnifiedRoutePayload | None:
    """LLM JSON dict → UnifiedRoutePayload. 파싱 불가 시 None."""
    lane = _parse_lane(raw.get("lane"))
    if lane is None:
        return None

    intent_raw = raw.get("intent")
    intent = intent_raw.strip().lower() if isinstance(intent_raw, str) else "unknown"

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

    conf_raw = raw.get("confidence")
    try:
        confidence = float(conf_raw) if conf_raw is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0

    slots = _normalize_media_slots(_parse_slots(raw.get("slots")))

    return UnifiedRoutePayload(
        intent=intent,
        lane=lane,
        goal=goal,
        task_type=task_type_str,
        slots=slots,
        risk_hint=risk_hint,
        needs_user_confirm=needs_confirm,
        clarification=clarification,
        confidence=confidence,
    )


def _build_dialogue_context_block(ctx: DialogueContext) -> str:
    pending_cu = "yes" if ctx.pending_cu is not None else "no"
    pending_prompt = ""
    if ctx.pending_cu is not None:
        pending_prompt = (ctx.pending_cu.prompt or ctx.pending_cu.goal or "")[:120]
    multi = is_multi_turn_active(ctx)
    return (
        f"dialogue_step={ctx.step.name}; pending_cu={pending_cu}; "
        f"pending_cu_prompt={pending_prompt!r}; multi_turn_active={multi}"
    )


def _payload_to_routed_turn(
    payload: UnifiedRoutePayload,
    user_text: str,
    catalog: list[dict[str, str]],
    *,
    fallback_kind: CommandKind,
) -> RoutedTurn:
    """UnifiedRoutePayload → RoutedTurn (catalog 검증·launch 폴백)."""
    kind = _kind_from_payload(payload, user_text, fallback=fallback_kind)
    slots = dict(payload.slots)
    if payload.task_type:
        slots.setdefault("task_type", payload.task_type)
    slots = normalize_routed_media_slots(slots)

    intent = payload.intent.strip().lower()
    lane = payload.lane

    # launch_app: catalog에 있는 app_key만 DIRECT_ACTION, 없으면 CU(search 금지)
    if intent == "launch_app" or (
        payload.task_type == "open_app" and lane is RouteLane.DIRECT_ACTION
    ):
        raw_key = str(slots.get("app_key") or "").strip()
        entry = _pick_catalog_entry(raw_key, catalog) if raw_key else None
        if entry is None and catalog:
            # LLM이 display_name만 넣은 경우
            disp = str(slots.get("display_name") or "").strip().lower()
            for c in catalog:
                if str(c.get("display_name", "")).strip().lower() == disp:
                    entry = c
                    break
        if entry is not None:
            slots["app_key"] = entry["app_key"]
            slots["display_name"] = entry["display_name"]
            return RoutedTurn(
                kind=CommandKind.APP_LAUNCH,
                lane=RouteLane.DIRECT_ACTION,
                goal=payload.goal,
                slots=slots,
                task_type=payload.task_type or "open_app",
                risk_hint=payload.risk_hint,
                needs_user_confirm=payload.needs_user_confirm,
                clarification=payload.clarification,
            )
        # catalog miss — Computer Use로 위임 (웹 검색 아님)
        goal = payload.goal or user_text.strip()
        slots.pop("app_key", None)
        return RoutedTurn(
            kind=CommandKind.COMPUTER_USE,
            lane=RouteLane.COMPUTER_USE,
            goal=goal,
            slots=slots,
            task_type=payload.task_type or "open_app",
            risk_hint=payload.risk_hint,
            needs_user_confirm=payload.needs_user_confirm,
            clarification=payload.clarification,
        )

    open_url = str(slots.get("url") or "").strip() or detect_open_url(user_text)
    if open_url and lane is RouteLane.DIRECT_ACTION:
        return RoutedTurn(
            kind=CommandKind.OPEN_URL,
            lane=RouteLane.DIRECT_ACTION,
            open_url=open_url,
            goal=payload.goal,
            slots=slots,
            task_type=payload.task_type,
            risk_hint=payload.risk_hint,
            needs_user_confirm=payload.needs_user_confirm,
            clarification=payload.clarification,
        )

    if lane is RouteLane.COMPUTER_USE:
        return RoutedTurn(
            kind=kind if kind is CommandKind.COMPUTER_USE else CommandKind.COMPUTER_USE,
            lane=RouteLane.COMPUTER_USE,
            goal=payload.goal or user_text.strip(),
            slots=slots,
            task_type=payload.task_type,
            risk_hint=payload.risk_hint,
            needs_user_confirm=payload.needs_user_confirm,
            clarification=payload.clarification,
        )

    return RoutedTurn(
        kind=kind,
        lane=lane,
        goal=payload.goal,
        slots=slots,
        task_type=payload.task_type,
        risk_hint=payload.risk_hint,
        needs_user_confirm=payload.needs_user_confirm,
        clarification=payload.clarification,
    )


def route_user_turn(
    user_text: str,
    ctx: DialogueContext,
    gemma: GemmaClient,
    *,
    assistant: IrisAssistant | None = None,
    app_catalog: list[dict[str, str]] | None = None,
    recent_turns: list[str] | None = None,
) -> RoutedTurn:
    """
    단일 진입점 — Gemma JSON 라우팅. 실패·오프라인 시 legacy_classify + resolve_route_lane.
    """
    text = user_text.strip()
    fallback_kind = legacy_classify_command(text)

    if is_multi_turn_active(ctx):
        push_activity_line("Router: multi-turn active — using legacy resolver.")
        return resolve_route_lane(text, fallback_kind, ctx)

    catalog = app_catalog
    if catalog is None and assistant is not None:
        catalog = resolve_app_candidates_for_llm(
            text,
            assistant._app_paths,
            db=assistant._db,
            top_k=8,
        )

    catalog = catalog or []
    catalog_json = json.dumps(catalog, ensure_ascii=False)
    recent_block = ""
    if recent_turns:
        recent_block = "recent_turns=" + json.dumps(recent_turns[-4:], ensure_ascii=False)

    hint_line = ""
    hint_raw = ctx.slots.get("last_execution_hint")
    if isinstance(hint_raw, str) and hint_raw.strip():
        hint_line = f"last_execution_hint={hint_raw.strip()[:80]!r}\n"

    user_block = (
        f"user_text={text!r}\n"
        f"{_build_dialogue_context_block(ctx)}\n"
        f"{hint_line}"
        f"app_catalog={catalog_json}\n"
        f"{recent_block}\n"
        "risk_policy: critical 작업은 needs_user_confirm=true"
    )

    messages = [
        ChatMessage(role="system", content=UNIFIED_ROUTER_SYSTEM),
        ChatMessage(role="user", content=user_block),
    ]
    push_activity_line("Router: unified LLM JSON routing call.")
    raw_reply = gemma.chat(messages, purpose=LlmPurpose.UNIFIED_ROUTER)
    if _is_llm_unavailable(raw_reply):
        push_activity_line("Router: unified classifier offline — legacy intent resolver.")
        return resolve_route_lane(text, fallback_kind, ctx)

    data = extract_json_object(raw_reply)
    if not data:
        push_activity_line("Router: unified JSON extract failed — legacy resolver.")
        return resolve_route_lane(text, fallback_kind, ctx)

    payload = parse_unified_route_json(data, text)
    if payload is None:
        push_activity_line("Router: unified payload invalid — legacy resolver.")
        return resolve_route_lane(text, fallback_kind, ctx)

    return _payload_to_routed_turn(payload, text, catalog, fallback_kind=fallback_kind)
