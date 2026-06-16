"""Hybrid Router 통합 흐름·폴백·모델 호출 예산 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from iris.assistant.frontier_agent import FrontierResult
from iris.assistant.route_analysis import OperationKind, RouteAnalysis, RouteOperation
from iris.assistant.router_policy import RouteLane, RoutedTurn
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext, DialogueStep
from tests.support.fakes import FakeGemma, RoutingGemma, make_routing_assistant, unified_router_json


def _complex_analysis(**extra: object) -> RouteAnalysis:
    base = {
        "primary_goal": "복합",
        "operations": (
            RouteOperation("op-1", OperationKind.RESPOND, "설명", None, None),
            RouteOperation("op-2", OperationKind.OPEN, "열기", "fs.open", "file"),
        ),
        "requires_user_response": True,
        "requires_execution": True,
        "requires_search": False,
        "requires_monitoring": False,
        "contains_conditional_flow": False,
        "contains_cross_capability_flow": True,
        "requested_capabilities": ("fs.open",),
        "confidence": 0.9,
        "analysis_incomplete": False,
    }
    base.update(extra)
    return RouteAnalysis(**base)  # type: ignore[arg-type]


def _hybrid_assistant(tmp_path: Path, gemma: RoutingGemma | FakeGemma):
    return make_test_assistant_hybrid(tmp_path, gemma)


def make_test_assistant_hybrid(tmp_path: Path, gemma):
    from tests.support.fakes import make_test_assistant

    return make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "unified_llm_router_enabled": True,
            "frontier_enabled": True,
            "frontier_complex_only": True,
            "chat_fast_path_enabled": True,
            "router_mode": "hybrid",
            "router_telemetry_enabled": False,
        },
        db_name="hybrid.db",
    )


# F 카테고리 — 복합 요청 (Frontier 5/5)
F_CATEGORY_CASES = [
    (
        "FastAPI가 뭔지 설명하고 프로젝트에서 관련 파일도 열어줘.",
        (
            RouteOperation("op-1", OperationKind.RESPOND, "설명", None, None),
            RouteOperation("op-2", OperationKind.OPEN, "열기", "fs.open", "proj"),
        ),
        True,
        True,
    ),
    (
        "최근 AI 뉴스를 찾아 요약하고 발표 문서에 정리해줘.",
        (
            RouteOperation("op-1", OperationKind.SEARCH, "검색", "web.search", "news"),
            RouteOperation(
                "op-2",
                OperationKind.CREATE,
                "정리",
                "doc.write",
                "doc",
                depends_on=("op-1",),
            ),
            RouteOperation(
                "op-3",
                OperationKind.VERIFY,
                "검증",
                "doc.verify",
                "doc",
                depends_on=("op-2",),
            ),
        ),
        True,
        True,
    ),
    (
        "현재 오류를 분석하고 코드를 수정한 다음 빌드와 테스트까지 해줘.",
        (
            RouteOperation("op-1", OperationKind.READ, "분석", "project.analyze", "code"),
            RouteOperation(
                "op-2",
                OperationKind.MODIFY,
                "수정",
                "fs.write",
                "code",
                depends_on=("op-1",),
            ),
            RouteOperation(
                "op-3",
                OperationKind.EXECUTE,
                "빌드",
                "project.build",
                "proj",
                depends_on=("op-2",),
            ),
            RouteOperation(
                "op-4",
                OperationKind.VERIFY,
                "테스트",
                "project.test",
                "proj",
                depends_on=("op-3",),
            ),
        ),
        True,
        True,
    ),
    (
        "이미지 생성이 끝났는지 확인하고 실패했으면 다시 실행해줘.",
        (
            RouteOperation("op-1", OperationKind.MONITOR, "확인", "task.monitor", "img"),
            RouteOperation(
                "op-2",
                OperationKind.EXECUTE,
                "재실행",
                "task.retry",
                "img",
                depends_on=("op-1",),
                conditional_on="op-1",
            ),
        ),
        True,
        True,
    ),
    (
        "최근 메일을 찾아 중요도를 판단하고 답장 초안까지 작성해줘.",
        (
            RouteOperation("op-1", OperationKind.SEARCH, "메일", "mail.search", "inbox"),
            RouteOperation(
                "op-2",
                OperationKind.READ,
                "판단",
                "mail.analyze",
                "inbox",
                depends_on=("op-1",),
            ),
            RouteOperation(
                "op-3",
                OperationKind.CREATE,
                "초안",
                "mail.compose",
                "draft",
                depends_on=("op-2",),
            ),
        ),
        True,
        True,
    ),
]


@pytest.mark.parametrize(
    "user_text,operations,resp,exec_flag",
    F_CATEGORY_CASES,
    ids=[f"f{i+1}" for i in range(5)],
)
def test_f_category_invokes_frontier_once(
    tmp_path: Path,
    user_text: str,
    operations: tuple[RouteOperation, ...],
    resp: bool,
    exec_flag: bool,
) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    analysis = RouteAnalysis(
        primary_goal=user_text,
        operations=operations,
        requires_user_response=resp,
        requires_search=any(op.kind is OperationKind.SEARCH for op in operations),
        requires_execution=exec_flag,
        requires_monitoring=any(op.kind is OperationKind.MONITOR for op in operations),
        contains_conditional_flow=any(op.conditional_on for op in operations),
        contains_cross_capability_flow=len({op.capability for op in operations if op.capability}) >= 2,
        requested_capabilities=tuple(sorted({op.capability for op in operations if op.capability})),
        confidence=0.9,
    )
    cached = RoutedTurn(
        kind=CommandKind.COMPUTER_USE,
        lane=RouteLane.CHAT_ONLY,
        goal=user_text,
        route_analysis=analysis,
        requires_frontier=True,
    )
    frontier = FrontierResult(
        user_reply="진행할게요.",
        needs_execution=True,
        routed_turn=RoutedTurn(
            kind=CommandKind.COMPUTER_USE,
            lane=RouteLane.COMPUTER_USE,
            goal=user_text,
        ),
        confidence=0.9,
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=cached,
    ) as mock_route, patch(
        "iris.assistant.turn_coordinator.run_frontier_turn",
        return_value=frontier,
    ) as mock_f, patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 완료",
    ):
        coord.run_turn(user_text)

    assert mock_route.call_count == 1
    mock_f.assert_called_once()


# 오탐 방지 — Frontier 호출 없음
NO_FRONTIER_CASES = [
    "파이썬 비동기 함수가 어떻게 작동하는지 자세히 설명해줘.",
    "다음 문장을 더 자연스럽고 읽기 쉽게 다듬어줘.",
    "최신 AI 뉴스를 찾아줘.",
    "메모장을 실행해줘.",
    "사용자가 제공한 글을 핵심 흐름 중심으로 요약해줘.",
]


@pytest.mark.parametrize("user_text", NO_FRONTIER_CASES)
def test_simple_requests_skip_frontier(tmp_path: Path, user_text: str) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        coord.run_turn(user_text)

    mock_f.assert_not_called()


def test_general_question_uses_unified_router(tmp_path: Path) -> None:
    gemma = RoutingGemma(
        chat_reply=unified_router_json(
            intent="chat",
            lane="chat_only",
            knowledge_lane="chat_only",
        ),
    )
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        result = coord.run_turn("파이썬이 뭐야?")

    mock_f.assert_not_called()
    assert result.delegate_dialogue_stream is True


def test_search_request_uses_unified_without_frontier(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    routed = RoutedTurn(
        kind=CommandKind.CURRENT_INFO_SEARCH,
        lane=RouteLane.SEARCH,
        slots={"query": "최신 AI 뉴스"},
        knowledge_lane="search",
        route_analysis=RouteAnalysis(
            primary_goal="검색",
            operations=(
                RouteOperation("op-1", OperationKind.SEARCH, "검색", "web.search", "news"),
                RouteOperation(
                    "op-2",
                    OperationKind.RESPOND,
                    "답변",
                    None,
                    None,
                    depends_on=("op-1",),
                ),
            ),
            requires_user_response=True,
            requires_search=True,
            requires_execution=False,
            requires_monitoring=False,
            contains_conditional_flow=False,
            contains_cross_capability_flow=False,
            requested_capabilities=("web.search",),
            confidence=0.9,
        ),
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=routed,
    ), patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        result = coord.run_turn("최신 AI 뉴스를 찾아줘")

    mock_f.assert_not_called()
    assert result.delegate_search is True


def test_frontier_failure_reuses_existing_unified_route(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    cached = RoutedTurn(
        kind=CommandKind.COMPUTER_USE,
        lane=RouteLane.COMPUTER_USE,
        goal="FastAPI 설명하고 파일 열기",
        requires_frontier=True,
    )

    with patch(
        "iris.assistant.turn_coordinator.run_frontier_turn",
        return_value=None,
    ), patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=cached,
    ) as mock_route, patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 완료",
    ):
        result = coord.run_turn(
            "FastAPI가 뭔지 설명하고 프로젝트의 관련 코드도 열어줘"
        )

    assert mock_route.call_count == 1
    assert result.route == RouteLane.COMPUTER_USE.value


def test_frontier_failure_does_not_call_unified_twice(tmp_path: Path) -> None:
    gemma = RoutingGemma(
        chat_reply=unified_router_json(
            intent="orchestrated",
            lane="orchestrated",
            requires_frontier=True,
        ),
    )
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch(
        "iris.assistant.turn_coordinator.run_frontier_turn",
        return_value=None,
    ), patch(
        "iris.assistant.turn_coordinator.route_user_turn",
    ) as mock_route, patch.object(
        assistant,
        "run_agent_loop",
        return_value="Iris: 계획 실행",
    ):
        coord.run_turn("현재 오류를 분석하고 코드를 수정한 다음 빌드와 테스트까지 해줘")

    assert mock_route.call_count == 1


def test_simple_chat_model_call_budget(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        coord.run_turn("안녕")

    mock_f.assert_not_called()
    router_calls = [
        c for c in gemma.calls if c and "Unified Router" in c[0].content
    ]
    assert len(router_calls) == 0


def test_pending_cu_is_handled_before_router(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    from iris.core.context_manager import PendingComputerUseGoal

    assistant.ctx.pending_cu = PendingComputerUseGoal(
        goal="test",
        risk_hint="low",
        prompt="진행할까요?",
    )
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.route_user_turn") as mock_route:
        result = coord.run_turn("취소")

    mock_route.assert_not_called()
    assert "취소" in result.user_visible


def test_multi_turn_mode_flow_is_preserved(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        result = coord.run_turn("작업 시작할게")

    mock_f.assert_not_called()
    assert result.route == RouteLane.MULTI_TURN.value
    assert assistant.ctx.step is DialogueStep.WORK_ASK_TASK


def test_explain_and_open_uses_frontier(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    cached = RoutedTurn(
        kind=CommandKind.COMPUTER_USE,
        lane=RouteLane.COMPUTER_USE,
        goal="설명하고 열기",
        requires_frontier=True,
    )
    routed = RoutedTurn(
        kind=CommandKind.COMPUTER_USE,
        lane=RouteLane.COMPUTER_USE,
        goal="설명하고 열기",
        requires_frontier=True,
    )
    frontier = FrontierResult(
        user_reply="알겠습니다.",
        needs_execution=True,
        routed_turn=routed,
        confidence=0.9,
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=cached,
    ), patch(
        "iris.assistant.turn_coordinator.run_frontier_turn",
        return_value=frontier,
    ) as mock_f, patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: 완료",
    ):
        coord.run_turn("FastAPI가 뭔지 설명하고 프로젝트의 관련 코드도 열어줘")

    mock_f.assert_called_once()


def test_no_fallback_loop(tmp_path: Path) -> None:
    """Frontier 실패 후 Unified 재호출 없음 — 턴당 route 1회."""
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    cached = RoutedTurn(
        kind=CommandKind.COMPUTER_USE,
        lane=RouteLane.COMPUTER_USE,
        goal="작업",
        requires_frontier=True,
        route_analysis=_complex_analysis(),
    )

    with patch(
        "iris.assistant.turn_coordinator.run_frontier_turn",
        return_value=None,
    ), patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=cached,
    ) as mock_route, patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="Iris: ok",
    ):
        for _ in range(2):
            coord.run_turn("복합 작업 해줘")

    assert mock_route.call_count == 2


def test_fast_path_miss_calls_unified_once(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    routed = RoutedTurn(
        kind=CommandKind.GENERAL_CHAT,
        lane=RouteLane.CHAT_ONLY,
        route_analysis=RouteAnalysis(
            primary_goal="설명",
            operations=(
                RouteOperation("op-1", OperationKind.RESPOND, "설명", None, None),
            ),
            requires_user_response=True,
            requires_search=False,
            requires_execution=False,
            requires_monitoring=False,
            contains_conditional_flow=False,
            contains_cross_capability_flow=False,
            requested_capabilities=(),
            confidence=0.9,
        ),
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=routed,
    ) as mock_route, patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        coord.run_turn("파이썬 제너레이터에 대해 설명해줘")

    mock_route.assert_called_once()
    mock_f.assert_not_called()


def test_unified_failure_has_bounded_fallback(tmp_path: Path) -> None:
    gemma = RoutingGemma(chat_reply="not json")
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    with patch("iris.assistant.turn_coordinator.run_frontier_turn") as mock_f:
        result = coord.run_turn("파이썬이 뭐야")

    mock_f.assert_not_called()
    assert result.delegate_dialogue_stream or result.route == RouteLane.CHAT_ONLY.value


def test_incomplete_route_analysis_invokes_frontier_once(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    incomplete = RouteAnalysis(
        primary_goal="x",
        operations=(),
        requires_user_response=False,
        requires_search=False,
        requires_execution=False,
        requires_monitoring=False,
        contains_conditional_flow=False,
        contains_cross_capability_flow=False,
        requested_capabilities=(),
        confidence=0.5,
        analysis_incomplete=True,
    )
    cached = RoutedTurn(
        kind=CommandKind.GENERAL_CHAT,
        lane=RouteLane.CHAT_ONLY,
        route_analysis=incomplete,
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=cached,
    ), patch(
        "iris.assistant.turn_coordinator.run_frontier_turn",
        return_value=None,
    ) as mock_f:
        coord.run_turn("모호한 요청")

    mock_f.assert_called_once()


def test_conflicting_chat_lane_and_operations_uses_frontier(tmp_path: Path) -> None:
    gemma = RoutingGemma()
    assistant = _hybrid_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    analysis = _complex_analysis(
        operations=(
            RouteOperation("op-1", OperationKind.RESPOND, "설명", None, None),
            RouteOperation("op-2", OperationKind.MODIFY, "수정", "fs.write", "src"),
            RouteOperation(
                "op-3",
                OperationKind.EXECUTE,
                "빌드",
                "project.build",
                "proj",
                depends_on=("op-2",),
            ),
        ),
    )
    cached = RoutedTurn(
        kind=CommandKind.GENERAL_CHAT,
        lane=RouteLane.CHAT_ONLY,
        route_analysis=analysis,
    )

    with patch(
        "iris.assistant.turn_coordinator.route_user_turn",
        return_value=cached,
    ), patch(
        "iris.assistant.turn_coordinator.run_frontier_turn",
        return_value=None,
    ) as mock_f:
        coord.run_turn("오류 수정하고 빌드해줘")

    mock_f.assert_called_once()
