"""현재 GemmaClient·IrisAssistant API 기준 테스트 더블."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

from iris.ai.gemma_client import ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.automation.action_executor import ActionExecutor
from iris.storage.database import Database
from tests.conftest import load_test_settings


def unified_router_json(**fields: object) -> str:
    payload: dict[str, Any] = {
        "intent": "chat",
        "lane": "chat_only",
        "goal": "",
        "slots": {},
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.9,
    }
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=False)


class FakeGemma:
    """GemmaClient 호환 mock — purpose= 키워드 수용."""

    def __init__(
        self,
        *,
        chat_reply: str = "안녕하세요!",
        planner_json: str | None = None,
        finalize: str | None = None,
    ) -> None:
        self.chat_reply = chat_reply
        self.planner_json = planner_json or '{"goal":"x","steps":[]}'
        self.finalize = finalize or chat_reply
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        purpose: object = None,
        **kwargs: object,
    ) -> str:
        self.calls.append(list(messages))
        if messages and "실행 계획기" in messages[0].content:
            return self.planner_json
        return self.finalize


class ApprovalGemma(FakeGemma):
    """LLM 승인 분류용 — JSON decision 반환."""

    def __init__(self, decision: str = "approve") -> None:
        super().__init__(chat_reply="")
        self._decision = decision

    def chat(
        self,
        messages: Sequence[ChatMessage],
        purpose: object = None,
        **kwargs: object,
    ) -> str:
        self.calls.append(list(messages))
        return f'{{"decision": "{self._decision}", "confidence": 0.92}}'


class RoutingGemma(FakeGemma):
    """Unified Router JSON 응답 — TurnCoordinator 테스트용."""

    def __init__(
        self,
        *,
        chat_reply: str = "안녕하세요!",
        planner_json: str | None = None,
        route_fn: Any | None = None,
    ) -> None:
        super().__init__(chat_reply=chat_reply, planner_json=planner_json)
        self._route_fn = route_fn

    def chat(
        self,
        messages: Sequence[ChatMessage],
        purpose: object = None,
        **kwargs: object,
    ) -> str:
        self.calls.append(list(messages))
        if not messages:
            return self.chat_reply
        sys = messages[0].content
        user = messages[-1].content if len(messages) > 1 else ""
        if self._route_fn is not None:
            return self._route_fn(sys, user)
        if "Unified Router" in sys:
            if "영화" in user:
                return unified_router_json(
                    intent="search",
                    lane="search",
                    goal="영화 정보",
                    slots={"query": "요즘 영화", "search_topic": "movie"},
                )
            if "Cursor" in user:
                return unified_router_json(
                    intent="computer_use",
                    lane="computer_use",
                    goal="Cursor 실행",
                )
            if "카톡" in user:
                return unified_router_json(
                    intent="computer_use",
                    lane="computer_use",
                    goal="카톡 메시지 전송",
                )
            if "유튜브" in user:
                return unified_router_json(
                    intent="computer_use",
                    lane="computer_use",
                    goal="유튜브 재생",
                    task_type="media_play",
                    slots={
                        "platform_hint": "youtube",
                        "media_action": "play",
                    },
                )
            if "사양" in user:
                return unified_router_json(
                    intent="fast_tool",
                    lane="fast_tool",
                    goal="시스템 사양",
                )
            if "작업 시작" in user:
                return unified_router_json(
                    intent="work_mode",
                    lane="multi_turn",
                    goal="작업 모드",
                )
            if "example.com" in user:
                return unified_router_json(
                    intent="computer_use",
                    lane="direct_action",
                    goal="URL 열기",
                    slots={"url": "https://example.com/page"},
                )
            if "안녕" in user:
                return unified_router_json(intent="chat", lane="chat_only", goal="인사")
            return unified_router_json(intent="chat", lane="chat_only")
        if "실행 계획기" in sys:
            return self.planner_json
        return self.chat_reply


def make_test_assistant(
    tmp_path: Path,
    gemma: FakeGemma | ApprovalGemma | RoutingGemma | Any,
    *,
    settings_overrides: dict[str, Any] | None = None,
    db_name: str = "iris_test.db",
) -> IrisAssistant:
    """load_test_settings 기반 IrisAssistant — 구버전 SimpleNamespace/settings 수동 생성 금지."""
    db = Database(path=tmp_path / db_name)
    defaults: dict[str, Any] = {
        "llm_intent_router_enabled": False,
        "unified_llm_router_enabled": False,
        "llm_approval_enabled": True,
        "chat_fast_path_enabled": False,
        "tts_enable_speech_formatter": False,
    }
    if settings_overrides:
        defaults.update(settings_overrides)
    settings = load_test_settings(tmp_path, **defaults)
    executor = ActionExecutor(db, {}, settings=settings)
    return IrisAssistant(db, executor, gemma, {}, settings)  # type: ignore[arg-type]


def make_routing_assistant(tmp_path: Path, gemma: RoutingGemma | FakeGemma) -> IrisAssistant:
    """Unified Router 켜진 TurnCoordinator용 assistant."""
    return make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "unified_llm_router_enabled": True,
            "chat_fast_path_enabled": True,
        },
        db_name="coord.db",
    )


def minimal_assistant_settings(**overrides: Any) -> Any:
    """Settings 없이 필요한 필드만 — 레거시 호환 (가급적 make_test_assistant 사용)."""
    base = {
        "llm_intent_router_enabled": False,
        "unified_llm_router_enabled": False,
        "llm_approval_enabled": True,
        "tts_enable_speech_formatter": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)
