"""Router 레인 정책 — CommandKind·DialogueStep·규칙으로 레인 결정 (LLM 최소화)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from iris.assistant.route_analysis import RouteAnalysis
from iris.assistant.tool_layer import is_search_intent
from iris.config.app_index import _alias_key
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext, DialogueStep
from iris.core.intent_router import route_user_intent

# 인사·잡담 — CHAT_ONLY (Gemma 대화 1회, Planner 생략)
_CHAT_ONLY_PATTERNS = re.compile(
    r"^(안녕|하이|헬로|반가워|고마워|감사|수고|뭐해|잘\s*자|굿밤|ㅎㅇ|"
    r"도움\s*줘|뭐\s*할\s*수\s*있|소개\s*해줘|이름\s*뭐)[\s!?。~]*$",
    re.IGNORECASE,
)

# 능력·소개 질문 (호출어 접두 허용)
_CAPABILITY_CHAT = re.compile(
    r"(뭐?|뭘)\s*할\s*수\s*있|할\s*수\s*있어|무엇을\s*할\s*수|능력이|도와줄\s*수|도움\s*줄\s*수",
    re.IGNORECASE,
)

# Fast path 제외 — 실행·검색·모드 의도 힌트
_FAST_PATH_EXEC_VERB = re.compile(
    r"(켜|열어|열\s|실행|검색|찾아|틀어|재생|보내|클릭|입력|삭제|설치|닫|종료|"
    r"실행해|켜줘|열어줘|해달라|부탁)",
    re.IGNORECASE,
)

_FAST_PATH_MODE_HINT = re.compile(
    r"(작업\s*시작|일해야|개발\s*시작|게임할|게임\s*시작|롤\s|창작\s*모드|작업\s*모드)",
    re.IGNORECASE,
)

# 명시 https URL만 DIRECT_ACTION open_url 힌트 (유튜브 홈 등 암시 URL은 CU 위임)
_OPEN_URL_MEDIA = re.compile(
    r"(https?://|www\.)[^\s]+|(틀어|재생해|들려).*(url|링크|주소)",
    re.IGNORECASE,
)

_MULTI_TURN_STEPS = frozenset(
    {
        DialogueStep.WORK_ASK_TASK,
        DialogueStep.WORK_ASK_APPS,
        DialogueStep.WORK_WAIT_APPROVAL,
        DialogueStep.GAME_ASK_TITLE,
        DialogueStep.GAME_ASK_SIDE_APPS,
        DialogueStep.GAME_WAIT_APPROVAL,
        DialogueStep.CREATIVE_ASK_TYPE,
        DialogueStep.CREATIVE_ASK_APPS,
        DialogueStep.CREATIVE_WAIT_APPROVAL,
        DialogueStep.ACTION_WAIT_APPROVAL,
        DialogueStep.MONITOR_WAIT_APPROVAL,
    }
)

_MODE_KINDS = frozenset(
    {
        CommandKind.WORK_MODE,
        CommandKind.GAME_MODE,
        CommandKind.CREATIVE_MODE,
    }
)

_COMPUTER_USE_KINDS = frozenset(
    {
        CommandKind.COMPUTER_USE,
        CommandKind.COMPLEX_AUTOMATION,
    }
)

_DIRECT_ACTION_KINDS = frozenset(
    {
        CommandKind.APP_LAUNCH,
        CommandKind.OPEN_URL,
        CommandKind.WINDOW_CONTROL,
        CommandKind.FILE_TASK,
        CommandKind.MONITORING_STATUS,
        CommandKind.COMPUTER_ACTION,
    }
)

_FAST_TOOL_KINDS = frozenset(
    {
        CommandKind.GET_SYSTEM_INFO,
    }
)


class RouteLane(str, Enum):
    """한 턴 처리 레인."""

    CHAT_ONLY = "CHAT_ONLY"
    HYBRID = "HYBRID"  # 검색 시도 후 부족분은 LLM 일반 지식으로 보완
    DIRECT_ACTION = "DIRECT_ACTION"
    FAST_TOOL = "FAST_TOOL"
    COMPUTER_USE = "COMPUTER_USE"
    ORCHESTRATED = "ORCHESTRATED"
    MULTI_TURN = "MULTI_TURN"
    SEARCH = "SEARCH"


@dataclass(frozen=True)
class RoutedTurn:
    """Router 출력 — Intent + 레인 + 선택적 직접 실행·CU 목표 힌트."""

    kind: CommandKind
    lane: RouteLane
    open_url: str | None = None  # DIRECT_ACTION 시 open_url 도구용 (명시 https만)
    goal: str | None = None  # COMPUTER_USE 시 CU에 전달할 목표 문장
    slots: Mapping[str, Any] = field(default_factory=dict)
    task_type: str | None = None
    risk_hint: str = "low"
    needs_user_confirm: bool = False
    clarification: str | None = None
    knowledge_lane: str | None = None  # chat_only | search | hybrid (지식 답변 3단)
    complexity: str | None = None  # simple | moderate | complex
    requires_frontier: bool = False
    complexity_reasons: tuple[str, ...] = ()
    route_analysis: RouteAnalysis | None = None


def is_chat_only(text: str, kind: CommandKind) -> bool:
    """규칙 기반 잡담·인사·능력 질문 판별 (액션·검색·모드 의도 제외)."""
    t = text.strip()
    if not t or kind is not CommandKind.GENERAL_CHAT:
        return False
    if _CHAT_ONLY_PATTERNS.search(t):
        return True
    if _CAPABILITY_CHAT.search(t) and not _FAST_PATH_EXEC_VERB.search(t):
        return True
    # 짧은 인사 (3~12자, 물음표/느낌표만)
    if len(t) <= 12 and re.match(r"^[가-힣a-zA-Z\s!?。~]+$", t):
        if any(w in t for w in ("안녕", "하이", "고마", "뭐해", "반가")):
            return True
    return False


def is_ambiguous_for_fast_path(text: str) -> bool:
    """
    대화 fast path를 쓰면 안 되는 발화 — 반드시 Unified/규칙 라우터로 보냄.
    실행 동사, URL, 모드 키워드, catalog 앱 힌트, GENERAL_CHAT 이외 intent.
    """
    t = text.strip()
    if not t:
        return True
    if detect_open_url(t):
        return True
    if _FAST_PATH_EXEC_VERB.search(t):
        return True
    if _FAST_PATH_MODE_HINT.search(t):
        return True
    if _alias_key(t) is not None:
        return True
    if route_user_intent(t) is not CommandKind.GENERAL_CHAT:
        return True
    return False


def detect_open_url(text: str) -> str | None:
    """명시 https URL만 반환. 앱·미디어 암시 발화는 CU(lane=computer_use)로 위임."""
    m = re.search(r"(https?://[^\s]+)", text)
    if m:
        return m.group(1).rstrip(".,)")
    return None


def is_multi_turn_active(ctx: DialogueContext) -> bool:
    return ctx.step in _MULTI_TURN_STEPS


def resolve_route_lane(
    text: str,
    kind: CommandKind,
    ctx: DialogueContext,
) -> RoutedTurn:
    """CommandKind + 대화 상태 → 처리 레인."""
    if is_search_intent(kind):
        return RoutedTurn(kind=kind, lane=RouteLane.SEARCH)

    if is_multi_turn_active(ctx):
        return RoutedTurn(kind=kind, lane=RouteLane.MULTI_TURN)

    if kind in _MODE_KINDS:
        return RoutedTurn(kind=kind, lane=RouteLane.MULTI_TURN)

    if is_chat_only(text, kind):
        return RoutedTurn(kind=kind, lane=RouteLane.CHAT_ONLY)

    if kind in _FAST_TOOL_KINDS:
        return RoutedTurn(kind=kind, lane=RouteLane.FAST_TOOL)

    url = detect_open_url(text)
    if url:
        return RoutedTurn(kind=kind, lane=RouteLane.DIRECT_ACTION, open_url=url)

    if kind in _COMPUTER_USE_KINDS:
        return RoutedTurn(kind=kind, lane=RouteLane.COMPUTER_USE, goal=text.strip() or None)

    if kind is CommandKind.OPEN_URL and not url:
        return RoutedTurn(
            kind=CommandKind.COMPUTER_USE,
            lane=RouteLane.COMPUTER_USE,
            goal=text.strip() or None,
        )

    if kind in _DIRECT_ACTION_KINDS:
        return RoutedTurn(kind=kind, lane=RouteLane.DIRECT_ACTION)

    # GENERAL_CHAT 등 — Orchestrator 기본 경로 대신 Computer Use
    return RoutedTurn(
        kind=kind if kind is not CommandKind.GENERAL_CHAT else CommandKind.COMPUTER_USE,
        lane=RouteLane.COMPUTER_USE,
        goal=text.strip() or None,
    )
