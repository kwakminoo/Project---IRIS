"""Deterministic Fast Path — 명시적 Intent Catalog, LLM 없이 단순 요청."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from iris.assistant.router_policy import (
    RouteLane,
    RoutedTurn,
    detect_open_url,
    is_ambiguous_for_fast_path,
    resolve_route_lane,
)
from iris.config.app_index import _alias_key, resolve_app_candidates_for_llm
from iris.core.command_router import CommandKind, classify_command
from iris.core.context_manager import DialogueContext
from iris.core.intent_router import route_user_intent

# 실행 신호 — 전체 요청이 단일 대화 Intent가 아닐 때 Fast Path 차단
_EXECUTION_SIGNAL = re.compile(
    r"(켜|열어|실행|검색|찾아|틀어|재생|보내|클릭|입력|삭제|설치|닫|종료|"
    r"빌드|테스트|수정|열어줘|켜줘|해달라|부탁|프로젝트|파일)",
    re.IGNORECASE,
)

_FILE_RISK = re.compile(
    r"(삭제|지워|설치|포맷|레지스트리|chmod|rm\s)",
    re.IGNORECASE,
)


def normalize_utterance(text: str) -> str:
    """한국어 어미·공백·구두점 정규화."""
    t = unicodedata.normalize("NFKC", text.strip().lower())
    t = re.sub(r"[!?。~…]+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


@dataclass(frozen=True)
class FastPathIntent:
    """단순 대화 Intent — 전체 발화가 이 패턴과만 일치할 때만 매칭."""

    intent_id: str
    utterance_patterns: tuple[re.Pattern[str], ...]
    response_lane: RouteLane = RouteLane.CHAT_ONLY
    blocked_when_execution_signal: bool = True


def _pat(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_FAST_PATH_INTENTS: tuple[FastPathIntent, ...] = (
    FastPathIntent(
        intent_id="greeting",
        utterance_patterns=(
            _pat(r"^(안녕|하이|헬로|반가워|ㅎㅇ|hello|hi)[\s!?]*$"),
        ),
    ),
    FastPathIntent(
        intent_id="gratitude",
        utterance_patterns=(
            _pat(r"^(고마워|감사|고맙|땡큐|thanks|thank you)[\s!?]*$"),
        ),
    ),
    FastPathIntent(
        intent_id="farewell",
        utterance_patterns=(
            _pat(r"^(잘\s*자|굿밤|잘자|bye|good\s*night)[\s!?]*$"),
        ),
    ),
    FastPathIntent(
        intent_id="praise",
        utterance_patterns=(
            _pat(r"^(수고했어|수고|고생했어)[\s!?]*$"),
        ),
    ),
    FastPathIntent(
        intent_id="identity",
        utterance_patterns=(
            _pat(r"^(너는\s*누구|넌\s*누구|이름이\s*뭐|아이리스는\s*누구)[\s?]*$"),
        ),
    ),
    FastPathIntent(
        intent_id="capability",
        utterance_patterns=(
            _pat(
                r"^(아이리스는?\s*)?(뭐|뭘)\s*할\s*수\s*있(어|나요|니|을까)[\s?]*$"
            ),
            _pat(r"^(뭐|뭘)\s*할\s*수\s*있(어|나요)[\s?]*$"),
            _pat(r"^무엇을\s*할\s*수\s*있(어|나요)[\s?]*$"),
        ),
    ),
)


@dataclass(frozen=True)
class FastPathDecision:
    """Fast Path 판별 결과."""

    matched: bool
    lane: RouteLane | None
    kind: CommandKind | None
    reason: str
    confidence: float
    direct_payload: Mapping[str, Any] = field(default_factory=dict)
    routed_turn: RoutedTurn | None = None


def _match_fast_path_intent(normalized: str) -> FastPathIntent | None:
    for intent in _FAST_PATH_INTENTS:
        for pat in intent.utterance_patterns:
            if pat.search(normalized):
                if intent.blocked_when_execution_signal and _EXECUTION_SIGNAL.search(
                    normalized
                ):
                    return None
                return intent
    return None


def _try_chat_intent_fast_path(
    text: str,
    ctx: DialogueContext,
) -> FastPathDecision | None:
    normalized = normalize_utterance(text)
    if not normalized:
        return None
    if _FILE_RISK.search(text):
        return None
    intent = _match_fast_path_intent(normalized)
    if intent is None:
        return None
    if is_ambiguous_for_fast_path(text):
        return None
    kind = route_user_intent(text)
    if kind is not CommandKind.GENERAL_CHAT:
        return None
    routed = RoutedTurn(kind=kind, lane=intent.response_lane)
    return FastPathDecision(
        matched=True,
        lane=intent.response_lane,
        kind=kind,
        reason=f"fast_intent_{intent.intent_id}",
        confidence=0.96,
        routed_turn=routed,
    )


def _try_native_action_fast_path(
    text: str,
    ctx: DialogueContext,
    *,
    app_paths: dict[str, str] | None = None,
    db: object | None = None,
) -> FastPathDecision | None:
    """명확한 Native 명령 — catalog 고신뢰 매칭만."""
    if _EXECUTION_SIGNAL.search(text) and route_user_intent(text) is CommandKind.GENERAL_CHAT:
        # 복합 문장 — Fast Path 제외
        if "," in text or "그리고" in text or "하고" in text:
            return None

    kind = classify_command(text)
    if kind in {
        CommandKind.FILE_TASK,
        CommandKind.COMPLEX_AUTOMATION,
        CommandKind.COMPUTER_USE,
        CommandKind.WEB_SEARCH,
        CommandKind.CURRENT_INFO_SEARCH,
        CommandKind.NEWS_SEARCH,
        CommandKind.WEATHER_SEARCH,
        CommandKind.MOVIE_SEARCH,
    }:
        return None

    if kind is CommandKind.GET_SYSTEM_INFO:
        routed = resolve_route_lane(text, kind, ctx)
        return FastPathDecision(
            matched=True,
            lane=routed.lane,
            kind=kind,
            reason="native_fast_tool_system_info",
            confidence=0.95,
            routed_turn=routed,
        )

    url = detect_open_url(text)
    if url:
        routed = RoutedTurn(
            kind=CommandKind.OPEN_URL,
            lane=RouteLane.DIRECT_ACTION,
            open_url=url,
        )
        return FastPathDecision(
            matched=True,
            lane=RouteLane.DIRECT_ACTION,
            kind=CommandKind.OPEN_URL,
            reason="native_open_url",
            confidence=0.98,
            routed_turn=routed,
        )

    if kind is CommandKind.APP_LAUNCH and app_paths is not None:
        alias = _alias_key(text)
        catalog: list[dict[str, str]] = resolve_app_candidates_for_llm(
            text, app_paths, db=db, top_k=3  # type: ignore[arg-type]
        )
        if len(catalog) == 1:
            entry = catalog[0]
            routed = RoutedTurn(
                kind=CommandKind.APP_LAUNCH,
                lane=RouteLane.DIRECT_ACTION,
                slots={
                    "app_key": entry["app_key"],
                    "display_name": entry.get("display_name", ""),
                },
            )
            return FastPathDecision(
                matched=True,
                lane=RouteLane.DIRECT_ACTION,
                kind=CommandKind.APP_LAUNCH,
                reason="native_launch_app_single_match",
                confidence=0.9,
                direct_payload={"app_key": entry["app_key"]},
                routed_turn=routed,
            )
        if alias and catalog:
            for entry in catalog:
                if str(entry.get("app_key", "")).lower() == alias.lower():
                    routed = RoutedTurn(
                        kind=CommandKind.APP_LAUNCH,
                        lane=RouteLane.DIRECT_ACTION,
                        slots={
                            "app_key": entry["app_key"],
                            "display_name": entry.get("display_name", ""),
                        },
                    )
                    return FastPathDecision(
                        matched=True,
                        lane=RouteLane.DIRECT_ACTION,
                        kind=CommandKind.APP_LAUNCH,
                        reason="native_launch_app_alias",
                        confidence=0.92,
                        routed_turn=routed,
                    )

    return None


def resolve_fast_path(
    text: str,
    ctx: DialogueContext,
    *,
    app_paths: dict[str, str] | None = None,
    db: object | None = None,
) -> FastPathDecision:
    """
    LLM 없이 확실한 단순 요청만 Fast Path.
    전체 발화가 단일 대화 Intent로 확정될 때만 matched=True.
    """
    t = text.strip()
    if not t:
        return FastPathDecision(
            matched=False,
            lane=None,
            kind=None,
            reason="empty_text",
            confidence=0.0,
        )

    chat = _try_chat_intent_fast_path(t, ctx)
    if chat is not None:
        return chat

    if app_paths is not None:
        native = _try_native_action_fast_path(t, ctx, app_paths=app_paths, db=db)
        if native is not None:
            return native

    return FastPathDecision(
        matched=False,
        lane=None,
        kind=None,
        reason="no_match",
        confidence=0.0,
    )
