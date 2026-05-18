"""TurnCoordinator 멀티-역할 파이프라인 테스트."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
from unittest.mock import patch

import pytest

from iris.ai.gemma_client import ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.router_policy import RouteLane, is_chat_only, resolve_route_lane
from iris.assistant.turn_coordinator import (
    TurnCoordinator,
    build_spoken_followup,
    build_user_visible,
)
from iris.automation.action_executor import ActionExecutor
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext, DialogueStep
from iris.core.intent_router import route_user_intent
from iris.storage.database import Database


class _FakeGemma:
    def __init__(
        self,
        *,
        chat_reply: str = "안녕하세요!",
        planner_json: str | None = None,
    ) -> None:
        self.chat_reply = chat_reply
        self.planner_json = planner_json or '{"goal":"x","steps":[]}'
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        if messages and "실행 계획기" in messages[0].content:
            return self.planner_json
        return self.chat_reply


def _make_assistant(tmp_path: Path, gemma: _FakeGemma) -> IrisAssistant:
    db = Database(path=tmp_path / "coord.db")
    executor = ActionExecutor(db, {})
    return IrisAssistant(db, executor, gemma, {})  # type: ignore[arg-type]


def test_is_chat_only_greeting() -> None:
    assert is_chat_only("안녕", CommandKind.GENERAL_CHAT)
    assert is_chat_only("고마워", CommandKind.GENERAL_CHAT)
    assert not is_chat_only("Cursor 열어줘", CommandKind.APP_LAUNCH)


def test_resolve_route_search() -> None:
    kind = route_user_intent("요즘 영화 뭐 있어")
    assert kind is CommandKind.MOVIE_SEARCH
    routed = resolve_route_lane("요즘 영화 뭐 있어", kind, DialogueContext())
    assert routed.lane is RouteLane.SEARCH


def test_chat_only_no_planner(tmp_path: Path) -> None:
    gemma = _FakeGemma(chat_reply="반가워요!")
    assistant = _make_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("안녕")

    assert result.route == RouteLane.CHAT_ONLY.value
    assert "반가워요" in result.user_visible
    assert not result.delegate_search
    planner_calls = [c for c in gemma.calls if c and "실행 계획기" in c[0].content]
    assert len(planner_calls) == 0


def test_app_launch_direct_action(tmp_path: Path) -> None:
    gemma = _FakeGemma()
    assistant = _make_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch.object(
        assistant,
        "handle_user_text",
        return_value="Iris: 요청을 실행합니다.\nCursor: 시작 (ok)",
    ) as mock_handle:
        result = coord.run_turn("Cursor 열어줘")

    assert result.route == RouteLane.DIRECT_ACTION.value
    assert result.early_ack is not None
    assert "Cursor" in result.user_visible or "실행" in result.user_visible
    mock_handle.assert_called_once()
    planner_calls = [c for c in gemma.calls if c and "실행 계획기" in c[0].content]
    assert len(planner_calls) == 0


def test_search_delegate(tmp_path: Path) -> None:
    gemma = _FakeGemma()
    assistant = _make_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("요즘 영화 뭐 있어")

    assert result.delegate_search is True
    assert result.search_intent_name == CommandKind.MOVIE_SEARCH.name
    assert result.user_visible == ""


def test_work_mode_multi_turn_no_immediate_launch(tmp_path: Path) -> None:
    gemma = _FakeGemma()
    assistant = _make_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("작업 시작할게")

    assert result.route == RouteLane.MULTI_TURN.value
    assert "어떤 작업" in result.user_visible or "최근" in result.user_visible
    assert assistant.ctx.step is DialogueStep.WORK_ASK_TASK


def test_direct_action_early_ack_before_execute(tmp_path: Path) -> None:
    gemma = _FakeGemma()
    assistant = _make_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    order: list[str] = []

    def on_ack(ack: str) -> None:
        order.append("early_ack")

    def _mock_execute(*_a: object, **_k: object) -> str:
        order.append("execute")
        return "Iris: 브라우저에서 URL을 열었습니다."

    with patch.object(assistant, "request_automation_tool", side_effect=_mock_execute):
        coord.run_turn("유튜브 틀어줘", on_early_ack=on_ack)

    assert order == ["early_ack", "execute"]


def test_youtube_open_url_direct(tmp_path: Path) -> None:
    gemma = _FakeGemma()
    assistant = _make_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch.object(
        assistant,
        "request_automation_tool",
        return_value="Iris: 브라우저에서 URL을 열었습니다.",
    ) as mock_tool:
        result = coord.run_turn("유튜브 틀어줘")

    assert result.route == RouteLane.DIRECT_ACTION.value
    assert "유튜브" in (result.early_ack or "")
    assert result.spoken_followup is not None
    assert "유튜브를 열게요" not in (result.spoken_followup or "")
    mock_tool.assert_called_once()
    args = mock_tool.call_args[0]
    assert args[0] == "open_url"
    assert args[1]["url"] == "https://www.youtube.com"
