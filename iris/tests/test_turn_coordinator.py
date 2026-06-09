"""TurnCoordinator 멀티-역할 파이프라인 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from iris.assistant.router_policy import (
    RouteLane,
    is_ambiguous_for_fast_path,
    is_chat_only,
    resolve_route_lane,
)
from iris.assistant.turn_coordinator import (
    TurnCoordinator,
    build_spoken_followup,
    build_user_visible,
)
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext, DialogueStep
from iris.core.intent_router import route_user_intent
from tests.support.fakes import FakeGemma, RoutingGemma, make_routing_assistant


def test_is_chat_only_greeting() -> None:
    assert is_chat_only("안녕", CommandKind.GENERAL_CHAT)
    assert is_chat_only("고마워", CommandKind.GENERAL_CHAT)
    assert is_chat_only("아이리스 넌 뭘 할 수 있어?", CommandKind.GENERAL_CHAT)
    assert not is_chat_only("Cursor 열어줘", CommandKind.APP_LAUNCH)


def test_is_ambiguous_for_fast_path() -> None:
    assert not is_ambiguous_for_fast_path("안녕")
    assert not is_ambiguous_for_fast_path("아이리스 넌 뭘 할 수 있어?")
    assert is_ambiguous_for_fast_path("메모장 켜줘")
    assert is_ambiguous_for_fast_path("https://example.com 열어")


def test_greeting_uses_unified_router_chat_only(tmp_path: Path) -> None:
    gemma = RoutingGemma(chat_reply="반가워요!")
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("안녕")

    assert result.route == RouteLane.CHAT_ONLY.value
    assert "반가워요" in result.user_visible
    router_calls = [
        c for c in gemma.calls if c and "Unified Router" in c[0].content
    ]
    assert len(router_calls) == 1


def test_ambiguous_uses_unified_router(tmp_path: Path) -> None:
    gemma = FakeGemma(
        chat_reply="ok",
    )
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    routed = resolve_route_lane(
        "메모장 켜줘",
        CommandKind.APP_LAUNCH,
        DialogueContext(),
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=routed,
    ) as mock_route:
        coord.run_turn("메모장 켜줘")

    mock_route.assert_called_once()


def test_resolve_route_search() -> None:
    kind = route_user_intent("요즘 영화 뭐 있어")
    assert kind is CommandKind.MOVIE_SEARCH
    routed = resolve_route_lane("요즘 영화 뭐 있어", kind, DialogueContext())
    assert routed.lane is RouteLane.SEARCH


def test_chat_only_no_planner(tmp_path: Path) -> None:
    gemma = RoutingGemma(chat_reply="반가워요!")
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("안녕")

    assert result.route == RouteLane.CHAT_ONLY.value
    assert "반가워요" in result.user_visible
    assert not result.delegate_search
    planner_calls = [c for c in gemma.calls if c and "실행 계획기" in c[0].content]
    assert len(planner_calls) == 0


def test_app_launch_direct_action(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 요청을 실행합니다.\nCursor: 시작 (ok)",
    ) as mock_cu:
        result = coord.run_turn("Cursor 열어줘")

    assert result.route == RouteLane.COMPUTER_USE.value
    mock_cu.assert_called_once()
    assert result.early_ack is not None
    assert "Cursor" in result.user_visible or "실행" in result.user_visible
    planner_calls = [c for c in gemma.calls if c and "실행 계획기" in c[0].content]
    assert len(planner_calls) == 0


def test_search_delegate(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("요즘 영화 뭐 있어")

    assert result.delegate_search is True
    assert result.search_intent_name == CommandKind.MOVIE_SEARCH.name
    assert result.user_visible == ""


def test_work_mode_multi_turn_no_immediate_launch(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("작업 시작할게")

    assert result.route == RouteLane.MULTI_TURN.value
    assert "어떤 작업" in result.user_visible or "최근" in result.user_visible
    assert assistant.ctx.step is DialogueStep.WORK_ASK_TASK


def test_direct_action_early_ack_before_execute(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    order: list[str] = []

    def on_ack(ack: str) -> None:
        order.append("early_ack")

    def _mock_cu(*_a: object, **_k: object) -> str:
        order.append("cu")
        return "Iris: 브라우저에서 URL을 열었습니다."

    with patch.object(assistant, "run_computer_use_loop", side_effect=_mock_cu):
        coord.run_turn("Cursor 열어줘", on_early_ack=on_ack)

    assert order == ["early_ack", "cu"]


def test_fast_tool_system_info_lane(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch.object(
        assistant,
        "request_automation_tool",
        return_value="Iris: 운영체제는 Windows, RAM 16GB.",
    ) as mock_tool:
        result = coord.run_turn("지금 컴퓨터 사양 어떻게 돼?")

    assert result.route == RouteLane.FAST_TOOL.value
    mock_tool.assert_called_once()
    args = mock_tool.call_args[0]
    assert args[0] == "get_system_info"


def test_computer_use_lane_multi_step(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 메시지를 보냈습니다.",
    ) as mock_cu:
        result = coord.run_turn("카톡 열고 철수에게 안녕이라고 보내줘")

    assert result.route == RouteLane.COMPUTER_USE.value
    mock_cu.assert_called_once()
    assert "메시지" in result.user_visible or "보냈" in result.user_visible


def test_discord_stays_direct_action(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    kind = route_user_intent("디스코드 켜줘")
    routed = resolve_route_lane("디스코드 켜줘", kind, DialogueContext())
    assert kind is CommandKind.APP_LAUNCH
    assert routed.lane is RouteLane.DIRECT_ACTION


def test_youtube_routes_computer_use(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 유튜브에서 재생을 시작했습니다.",
    ) as mock_cu:
        result = coord.run_turn("유튜브 틀어줘")

    assert result.route == RouteLane.COMPUTER_USE.value
    mock_cu.assert_called_once()
    goal = mock_cu.call_args.kwargs.get("goal") or ""
    assert "유튜브" in goal
    assert "재생" in result.user_visible or "유튜브" in result.user_visible


def test_computer_use_early_ack_before_cu(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    order: list[str] = []

    def on_ack(ack: str) -> None:
        order.append("early_ack")

    def _mock_cu(*_a: object, **_k: object) -> str:
        order.append("cu")
        return "Iris: 작업을 마쳤습니다."

    with patch.object(assistant, "run_computer_use_loop", side_effect=_mock_cu):
        result = coord.run_turn("유튜브에서 아이유 틀어줘", on_early_ack=on_ack)

    assert order == ["early_ack", "cu"]
    assert result.early_ack is not None
    assert len((result.early_ack or "").strip()) > 0
    assert "마쳤" not in (result.early_ack or "")
    assert "마쳤" in result.user_visible


def test_explicit_https_still_direct_action(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = make_routing_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    url = "https://example.com/page"

    with patch.object(
        assistant,
        "request_automation_tool",
        return_value="Iris: 브라우저에서 URL을 열었습니다.",
    ) as mock_tool:
        result = coord.run_turn(f"이 링크 열어줘 {url}")

    assert result.route == RouteLane.DIRECT_ACTION.value
    mock_tool.assert_called_once()
    assert mock_tool.call_args[0][1]["url"] == url
