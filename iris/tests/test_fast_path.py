"""Fast Path 단위 테스트."""

from __future__ import annotations

from iris.assistant.fast_path import resolve_fast_path
from iris.assistant.router_policy import RouteLane
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext


def test_greeting_uses_fast_chat_path() -> None:
    fast = resolve_fast_path("안녕", DialogueContext())
    assert fast.matched
    assert fast.lane is RouteLane.CHAT_ONLY


def test_thanks_uses_fast_chat_path() -> None:
    fast = resolve_fast_path("고마워", DialogueContext())
    assert fast.matched
    assert fast.lane is RouteLane.CHAT_ONLY


def test_capability_question_uses_fast_chat_path() -> None:
    fast = resolve_fast_path("아이리스는 뭘 할 수 있어?", DialogueContext())
    assert fast.matched
    assert fast.lane is RouteLane.CHAT_ONLY


def test_ambiguous_action_does_not_use_fast_path() -> None:
    fast = resolve_fast_path("메모장 켜줘", DialogueContext(), app_paths={})
    assert not fast.matched


def test_exclude_signal_blocks_fast_path() -> None:
    fast = resolve_fast_path(
        "파이썬이 뭔지 설명하고 관련 파일도 열어줘",
        DialogueContext(),
    )
    assert not fast.matched


def test_compound_chat_and_execution_not_fast_path() -> None:
    fast = resolve_fast_path(
        "수고했어, 이제 프로젝트를 빌드해줘.",
        DialogueContext(),
    )
    assert not fast.matched


def test_praise_alone_uses_fast_path() -> None:
    fast = resolve_fast_path("수고했어", DialogueContext())
    assert fast.matched
    assert fast.reason == "fast_intent_praise"


def test_search_intent_not_fast_path() -> None:
    fast = resolve_fast_path("최신 AI 뉴스 찾아줘", DialogueContext())
    assert not fast.matched
