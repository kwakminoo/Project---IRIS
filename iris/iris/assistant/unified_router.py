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
from iris.assistant.search_routing import command_kind_for_search_slots
from iris.config.app_index import resolve_app_candidates_for_llm
from iris.core.activity_sink import push_activity_line
from iris.core.command_router import CommandKind
from iris.assistant.media_completion import normalize_routed_media_slots
from iris.assistant.action_skills import clarify_missing_skill_slots
from iris.core.context_manager import DialogueContext

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant

UNIFIED_ROUTER_SYSTEM = """당신은 Iris Unified Router입니다. 사용자 발화를 분석해 JSON만 출력하세요.
역할: (1) 지식 답변 방식 knowledge_lane, (2) PC 실행 방식 lane·intent·slots를 결정합니다.
실행 방법·버튼 경로·키보드 단축키는 쓰지 마세요.
=== knowledge_lane (지식 답변 3단) — 가장 먼저 결정 ===
A) chat_only — 검색 없이 로컬 LLM만
- 순수 인사·감사·잡담·능력 소개·의견·창작·코딩 아이디어·일반 조언
- 최신 사실·가격·순위·출시일·법/의료/금융 확정 답이 필요 없는 대화
- 사용자가 "지금/오늘/최신/요즘/2024/2025/2026" 등 시점을 요구하지 않음
B) search — 웹 검색 후 근거 기반 답변 (기본: 사실·정의·비교·최신)
- "~가 뭐야", "~란", 정의·설명·백과형 질문 (단일 개념도 search 우선)
- 두 개 이상 대상 비교: "A와 B 차이", "vs", "뭐가 나아", "장단점"
- 날씨·뉴스·영화·주가·환율·이벤트·제품 스펙·버전·가격 등 시점 민감 정보
- 숫자·날짜·순위·인용이 중요한 질문
- 사용자가 "검색해", "찾아봐", "출처", "근거"를 요구
C) hybrid — 검색 시도 + 부족하면 모델 지식으로 보완 (불확실·복합 질문)
- search만으로는 맥락이 부족해 보이지만 답은 필요한 경우
- 역사+최신 혼합, 넓은 주제("AI 시장 전망"), 다단계 설명+사실 혼합
- 비교이지만 한쪽이 매우 생소하거나 질문이 모호한 경우
- confidence < 0.75 이고 사실 검증이 도움이 될 때
우선순위 (충돌 시):
1) PC 실행 의도(앱 실행·CU·미디어)가 있으면 knowledge_lane은 보조 — 실행 lane 우선
2) 비교·vs·차이·두 고유명사 → search (chat_only 금지)
3) 최신·숫자·날짜 요구 → search
4) 단순 인사·잡담 → chat_only
5) 애매하면 hybrid (search보다 chat_only를 기본으로 두지 말 것)
=== 실행 라우팅 (기존과 동일) ===
- 로컬 PC 앱 실행 → intent=launch_app, lane=direct_action, slots.app_key는 app_catalog만. 없으면 computer_use, search 금지.
- 멀티 스텝 PC 조작 → intent=computer_use, lane=computer_use.
- 미디어 검색/재생 → intent=computer_use, lane=computer_use, task_type=media_play, slots.platform_hint·media_action·search_query 필수.
- PC 사양 → intent=fast_tool, lane=fast_tool.
- 작업/게임/창작 모드 → intent=work_mode|game_mode|creative_mode, lane=multi_turn.
- 명시 https URL → slots.url, lane=direct_action 가능.
- critical → risk_hint=critical, needs_user_confirm=true.
pending_cu가 있으면 approve_followup|reject_followup|clarify|unrelated.
=== search / hybrid 슬롯 규칙 ===
- slots.query: 주 검색어 1개 (짧은 키워드, 한국어 또는 영어, 2~8단어)
- slots.queries: 추가 검색어 배열 (비교 시 필수, 2~4개)
  예) "GPT vs Gemini" → queries: ["GPT large language model", "Google Gemini model", "GPT vs Gemini differences"]
- slots.search_topic: general | weather | news | movie | current_info | comparison | definition
- slots.answer_shape: definition | comparison | summary | how_to | list
- 비교(comparison)일 때 queries는 최소 2개, 각 대상을 분리해 검색 가능하게 작성
=== 검색 수집 정책 — 운영용 참고 문구 ===
- 웹 검색 우선순위: DuckDuckGo(ddgs 패키지) → Playwright Google SERP(폴백, IRIS_SEARCH_PLAYWRIGHT_FALLBACK=1일 때만)
- Router slots.query / slots.queries에는 위 백엔드로 전달될 검색어만 담습니다. (LLM 답변 프롬프트/검증 문구가 아님)
미디어 슬롯 (변경 없음):
- task_type=media_play, platform_hint, media_action, search_query, success_criteria 등 기존 규칙 준수.
JSON 스키마(엄격):
{
  "intent": "chat|search|launch_app|computer_use|fast_tool|work_mode|game_mode|creative_mode|monitoring|approve_followup|reject_followup|clarify|unrelated",
  "lane": "chat_only|search|hybrid|direct_action|computer_use|fast_tool|multi_turn",
  "knowledge_lane": "chat_only|search|hybrid",
  "goal": "한국어 실행·답변 목표 한 문장",
  "task_type": "open_app|compose_text|media_play|send_message|file|window|multi_step|knowledge|unknown",
  "slots": {
    "app_key": "",
    "display_name": "",
    "text_to_type": "",
    "message_text": "",
    "recipient": "",
    "query": "",
    "queries": [],
    "search_topic": "general|weather|news|movie|current_info|comparison|definition",
    "answer_shape": "definition|comparison|summary|how_to|list",
    "url": "",
    "platform_hint": "youtube|spotify|netflix|browser|unknown",
    "media_action": "search|play",
    "search_query": "",
    "success_criteria": "search_results_visible|playback_confirmed",
    "skill_id": "",
    "user_request_summary": ""
  },
  "risk_hint": "low|medium|high|critical",
  "needs_user_confirm": false,
  "clarification": null,
  "confidence": 0.0
}
규칙:
- knowledge_lane=search 이면 lane도 search (PC 실행 제외).
- knowledge_lane=hybrid 이면 lane=hybrid (PC 실행 제외).
- knowledge_lane=chat_only 이면 lane=chat_only (PC 실행 제외).
- PC 실행 intent가 있으면 knowledge_lane은 무시해도 됨.
- 다른 텍스트 없이 JSON만 출력하세요.
"""

_LANE_MAP: dict[str, RouteLane] = {
    "chat_only": RouteLane.CHAT_ONLY,
    "search": RouteLane.SEARCH,
    "hybrid": RouteLane.HYBRID,
    "direct_action": RouteLane.DIRECT_ACTION,
    "computer_use": RouteLane.COMPUTER_USE,
    "fast_tool": RouteLane.FAST_TOOL,
    "multi_turn": RouteLane.MULTI_TURN,
}

_KNOWLEDGE_LANE_MAP: dict[str, RouteLane] = {
    "chat_only": RouteLane.CHAT_ONLY,
    "search": RouteLane.SEARCH,
    "hybrid": RouteLane.HYBRID,
}

# PC 실행 intent — knowledge_lane으로 lane을 덮어쓰지 않음
_PC_EXEC_INTENTS = frozenset(
    {
        "launch_app",
        "computer_use",
        "fast_tool",
        "work_mode",
        "game_mode",
        "creative_mode",
        "monitoring",
        "approve_followup",
        "reject_followup",
    }
)


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
    knowledge_lane: str | None = None


def _is_llm_unavailable(text: str) -> bool:
    return text.strip() == FALLBACK_KO or text.strip().startswith("로컬 언어 모델")


def _parse_lane(raw: object) -> RouteLane | None:
    if not isinstance(raw, str):
        return None
    return _LANE_MAP.get(raw.strip().lower())


def _parse_knowledge_lane(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    if key in _KNOWLEDGE_LANE_MAP:
        return key
    return None


def _parse_slots(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if v is None:
            continue
        key = str(k)
        if key == "queries" and isinstance(v, list):
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            if cleaned:
                out[key] = cleaned
            continue
        if isinstance(v, str) and not v.strip():
            continue
        out[key] = v
    return out


def _sync_knowledge_lane_to_lane(
    intent: str,
    lane: RouteLane,
    knowledge_lane: str | None,
) -> RouteLane:
    """지식 3단 — PC 실행이 아니면 knowledge_lane이 lane을 결정."""
    if intent in _PC_EXEC_INTENTS:
        return lane
    if knowledge_lane and knowledge_lane in _KNOWLEDGE_LANE_MAP:
        return _KNOWLEDGE_LANE_MAP[knowledge_lane]
    return lane


def _pick_catalog_entry(
    app_key: str,
    catalog: list[dict[str, str]],
) -> dict[str, str] | None:
    key = app_key.strip().lower()
    for entry in catalog:
        if str(entry.get("app_key", "")).strip().lower() == key:
            return entry
    return None


def _safe_chat_fallback_routed_turn(user_text: str) -> RoutedTurn:
    """Unified Router 오프라인·JSON 실패 시 — regex 휴리스틱 대신 안전한 대화 레인."""
    return RoutedTurn(
        kind=CommandKind.GENERAL_CHAT,
        lane=RouteLane.CHAT_ONLY,
        goal=user_text.strip() or None,
        knowledge_lane="chat_only",
    )


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
    if intent == "search" or payload.lane in (RouteLane.SEARCH, RouteLane.HYBRID):
        return command_kind_for_search_slots(payload.slots)
    if intent == "monitoring":
        return CommandKind.MONITORING_STATUS
    if intent in {"computer_use", "approve_followup", "reject_followup", "clarify"}:
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

    knowledge_lane = _parse_knowledge_lane(raw.get("knowledge_lane"))
    lane = _sync_knowledge_lane_to_lane(intent, lane, knowledge_lane)

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
        knowledge_lane=knowledge_lane,
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


def _routed_turn_common_fields(payload: UnifiedRoutePayload) -> dict[str, Any]:
    return {
        "goal": payload.goal,
        "task_type": payload.task_type,
        "risk_hint": payload.risk_hint,
        "needs_user_confirm": payload.needs_user_confirm,
        "clarification": payload.clarification,
        "knowledge_lane": payload.knowledge_lane,
    }


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
    common = _routed_turn_common_fields(payload)

    intent = payload.intent.strip().lower()
    lane = payload.lane

    # launch_app: catalog에 있는 app_key만 DIRECT_ACTION, 없으면 CU(search 금지)
    if intent == "launch_app" or (
        payload.task_type == "open_app" and lane is RouteLane.DIRECT_ACTION
    ):
        raw_key = str(slots.get("app_key") or "").strip()
        entry = _pick_catalog_entry(raw_key, catalog) if raw_key else None
        if entry is None and catalog:
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
                slots=slots,
                **common,
            )
        slots.pop("app_key", None)
        cu_common = {**common, "goal": payload.goal or user_text.strip()}
        return RoutedTurn(
            kind=CommandKind.COMPUTER_USE,
            lane=RouteLane.COMPUTER_USE,
            slots=slots,
            **cu_common,
        )

    open_url = str(slots.get("url") or "").strip() or detect_open_url(user_text)
    if open_url and lane is RouteLane.DIRECT_ACTION:
        return RoutedTurn(
            kind=CommandKind.OPEN_URL,
            lane=RouteLane.DIRECT_ACTION,
            open_url=open_url,
            slots=slots,
            **common,
        )

    if lane is RouteLane.COMPUTER_USE:
        cu_common = {**common, "goal": payload.goal or user_text.strip()}
        slot_clarify = clarify_missing_skill_slots(payload.task_type, slots)
        if slot_clarify:
            clarify_common = {
                k: v for k, v in common.items() if k not in ("clarification", "goal")
            }
            return RoutedTurn(
                kind=CommandKind.GENERAL_CHAT,
                lane=RouteLane.CHAT_ONLY,
                goal=slot_clarify,
                slots=slots,
                clarification=slot_clarify,
                **clarify_common,
            )
        return RoutedTurn(
            kind=kind if kind is CommandKind.COMPUTER_USE else CommandKind.COMPUTER_USE,
            lane=RouteLane.COMPUTER_USE,
            slots=slots,
            **cu_common,
        )

    return RoutedTurn(
        kind=kind,
        lane=lane,
        slots=slots,
        **common,
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
    단일 진입점 — Gemma JSON 라우팅.
    실패·오프라인 시 regex 휴리스틱 대신 CHAT_ONLY 안전 폴백(멀티턴은 상태 기반 resolve만).
    """
    text = user_text.strip()

    if is_multi_turn_active(ctx):
        push_activity_line("Router: multi-turn active — lane from dialogue step.")
        kind = CommandKind.GENERAL_CHAT
        if ctx.step.name.startswith("WORK"):
            kind = CommandKind.WORK_MODE
        elif ctx.step.name.startswith("GAME"):
            kind = CommandKind.GAME_MODE
        elif ctx.step.name.startswith("CREATIVE"):
            kind = CommandKind.CREATIVE_MODE
        return resolve_route_lane(text, kind, ctx)

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
        push_activity_line("Router: unified classifier offline — chat_only fallback.")
        return _safe_chat_fallback_routed_turn(text)

    data = extract_json_object(raw_reply)
    if not data:
        push_activity_line("Router: unified JSON extract failed — chat_only fallback.")
        return _safe_chat_fallback_routed_turn(text)

    payload = parse_unified_route_json(data, text)
    if payload is None:
        push_activity_line("Router: unified payload invalid — chat_only fallback.")
        return _safe_chat_fallback_routed_turn(text)

    return _payload_to_routed_turn(
        payload, text, catalog, fallback_kind=CommandKind.GENERAL_CHAT
    )
