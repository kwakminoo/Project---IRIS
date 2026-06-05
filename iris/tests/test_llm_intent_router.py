"""LLM Intent Router 단위 테스트 (FakeGemma)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Sequence

from iris.ai.gemma_client import ChatMessage
from iris.assistant.llm_intent_router import (
    INTENT_ROUTER_SYSTEM,
    parse_llm_intent_json,
    route_with_llm,
)
from iris.assistant.router_policy import RouteLane, detect_open_url, resolve_route_lane
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext


class _FakeGemma:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        return self.reply


def test_parse_llm_intent_computer_use() -> None:
    raw = {
        "lane": "computer_use",
        "goal": "유튜브에서 재생 목록을 틀어줘",
        "task_type": "media_play",
        "slots": {"app_hint": "youtube"},
        "risk_hint": "low",
        "needs_user_confirm": False,
    }
    intent = parse_llm_intent_json(raw, "유튜브 틀어줘")
    assert intent is not None
    assert intent.lane is RouteLane.COMPUTER_USE
    assert intent.goal == "유튜브에서 재생 목록을 틀어줘"
    assert intent.task_type == "media_play"
    assert intent.slots.get("app_hint") == "youtube"


def test_detect_open_url_no_youtube_home() -> None:
    assert detect_open_url("유튜브 틀어줘") is None
    assert detect_open_url("https://www.youtube.com/watch?v=abc") == (
        "https://www.youtube.com/watch?v=abc"
    )


def test_route_with_llm_computer_use_not_overridden_by_url() -> None:
    gemma = _FakeGemma(
        '{"lane":"computer_use","goal":"유튜브에서 음악을 재생해줘",'
        '"task_type":"media_play","slots":{},"risk_hint":"low","needs_user_confirm":false}'
    )
    routed = route_with_llm("유튜브 틀어줘", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.COMPUTER_USE
    assert routed.goal == "유튜브에서 음악을 재생해줘"
    assert routed.open_url is None
    assert gemma.calls[0][0].content == INTENT_ROUTER_SYSTEM


def test_route_with_llm_fallback_on_bad_json() -> None:
    gemma = _FakeGemma("안녕하세요")
    routed = route_with_llm("디스코드 켜줘", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.CHAT_ONLY
    assert routed.kind is CommandKind.GENERAL_CHAT


def test_route_with_llm_search_lane() -> None:
    gemma = _FakeGemma(
        '{"lane":"search","goal":"최신 영화 정보 검색","task_type":"unknown",'
        '"slots":{"query":"요즘 영화","search_topic":"movie"},'
        '"risk_hint":"low","needs_user_confirm":false}'
    )
    routed = route_with_llm("요즘 영화 뭐 있어", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.SEARCH
    assert routed.kind is CommandKind.MOVIE_SEARCH


def test_route_with_llm_critical_confirm() -> None:
    gemma = _FakeGemma(
        '{"lane":"computer_use","goal":"시스템 파일 삭제","task_type":"file",'
        '"slots":{},"risk_hint":"critical","needs_user_confirm":true,'
        '"clarification":"삭제를 진행할까요?"}'
    )
    routed = route_with_llm("다운로드 폴더 전부 삭제해", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.needs_user_confirm is True
    assert routed.clarification == "삭제를 진행할까요?"
