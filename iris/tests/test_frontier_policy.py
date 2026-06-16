"""Frontier 복합 판별 정책 테스트 — RouteAnalysis 기반."""

from __future__ import annotations

from iris.assistant.frontier_policy import evaluate_frontier_need
from iris.assistant.route_analysis import OperationKind, RouteAnalysis, RouteOperation
from iris.assistant.router_policy import RouteLane, RoutedTurn
from iris.config.settings import RouterMode
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueContext


def _routed(lane: RouteLane, **kwargs: object) -> RoutedTurn:
    return RoutedTurn(kind=CommandKind.GENERAL_CHAT, lane=lane, **kwargs)  # type: ignore[arg-type]


def _analysis(**kwargs: object) -> RouteAnalysis:
    defaults = {
        "primary_goal": "test",
        "operations": (),
        "requires_user_response": False,
        "requires_search": False,
        "requires_execution": False,
        "requires_monitoring": False,
        "contains_conditional_flow": False,
        "contains_cross_capability_flow": False,
        "requested_capabilities": (),
        "confidence": 0.9,
        "analysis_incomplete": False,
    }
    defaults.update(kwargs)
    return RouteAnalysis(**defaults)  # type: ignore[arg-type]


def _ops(*items: RouteOperation) -> tuple[RouteOperation, ...]:
    return items


def test_simple_greeting_no_frontier() -> None:
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.RESPOND, "인사", None, None)
        ),
        requires_user_response=True,
    )
    d = evaluate_frontier_need(
        user_text="안녕",
        routed=_routed(RouteLane.CHAT_ONLY, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert not d.use_frontier


def test_simple_search_no_frontier() -> None:
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.SEARCH, "뉴스 검색", "web.search", "query"),
            RouteOperation(
                "op-2",
                OperationKind.RESPOND,
                "요약",
                None,
                None,
                depends_on=("op-1",),
            ),
        ),
        requires_search=True,
        requires_user_response=True,
    )
    d = evaluate_frontier_need(
        user_text="최신 AI 뉴스 찾아줘",
        routed=_routed(RouteLane.SEARCH, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert not d.use_frontier


def test_explain_and_open_uses_frontier() -> None:
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.RESPOND, "FastAPI 설명", None, None),
            RouteOperation(
                "op-2",
                OperationKind.OPEN,
                "파일 열기",
                "filesystem.open",
                "project",
                depends_on=(),
            ),
        ),
        requires_user_response=True,
        requires_execution=True,
        contains_cross_capability_flow=True,
    )
    d = evaluate_frontier_need(
        user_text="FastAPI가 뭔지 설명하고 프로젝트 관련 파일도 열어줘",
        routed=_routed(RouteLane.CHAT_ONLY, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert d.use_frontier
    assert d.reason in (
        "response_and_execution",
        "cross_capability_flow",
        "complex_operation_graph",
    )


def test_search_summarize_and_send_uses_frontier() -> None:
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.SEARCH, "메일 검색", "mail.search", "inbox"),
            RouteOperation(
                "op-2",
                OperationKind.CREATE,
                "답장 초안",
                "mail.compose",
                "draft",
                depends_on=("op-1",),
            ),
        ),
        requires_search=True,
        requires_execution=True,
        contains_cross_capability_flow=True,
    )
    d = evaluate_frontier_need(
        user_text="최근 메일을 찾아 요약하고 답장 초안까지 만들어줘",
        routed=_routed(RouteLane.ORCHESTRATED, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert d.use_frontier


def test_orchestrated_lane_uses_frontier() -> None:
    d = evaluate_frontier_need(
        user_text="복합 작업",
        routed=_routed(
            RouteLane.ORCHESTRATED,
            requires_frontier=True,
            complexity_reasons=("orchestrated_lane",),
        ),
        ctx=DialogueContext(),
    )
    assert d.use_frontier


def test_long_sentence_alone_does_not_require_frontier() -> None:
    text = "파이썬은 " + "매우 유용한 " * 20 + "프로그래밍 언어입니다."
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.RESPOND, "설명", None, None)
        ),
        requires_user_response=True,
    )
    d = evaluate_frontier_need(
        user_text=text,
        routed=_routed(RouteLane.CHAT_ONLY, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert not d.use_frontier


def test_simple_translation_no_frontier() -> None:
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.RESPOND, "문장 다듬기", None, None)
        ),
        requires_user_response=True,
    )
    d = evaluate_frontier_need(
        user_text="이 문장을 자연스럽게 고쳐줘",
        routed=_routed(RouteLane.CHAT_ONLY, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert not d.use_frontier


def test_incomplete_analysis_invokes_frontier() -> None:
    analysis = _analysis(analysis_incomplete=True)
    d = evaluate_frontier_need(
        user_text="모호한 요청",
        routed=_routed(RouteLane.CHAT_ONLY, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert d.use_frontier
    assert d.reason == "incomplete_structured_analysis"


def test_conflicting_chat_lane_and_operations_uses_frontier() -> None:
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.RESPOND, "설명", None, None),
            RouteOperation("op-2", OperationKind.MODIFY, "코드 수정", "fs.write", "src"),
            RouteOperation(
                "op-3",
                OperationKind.EXECUTE,
                "빌드",
                "project.build",
                "proj",
                depends_on=("op-2",),
            ),
        ),
        requires_user_response=True,
        requires_execution=True,
        contains_cross_capability_flow=True,
    )
    d = evaluate_frontier_need(
        user_text="오류 수정하고 빌드해줘",
        routed=_routed(RouteLane.CHAT_ONLY, route_analysis=analysis),
        ctx=DialogueContext(),
    )
    assert d.use_frontier


def test_unified_only_mode_skips_frontier() -> None:
    analysis = _analysis(
        operations=_ops(
            RouteOperation("op-1", OperationKind.RESPOND, "x", None, None),
            RouteOperation("op-2", OperationKind.EXECUTE, "y", "cu", None),
        ),
        requires_user_response=True,
        requires_execution=True,
    )
    d = evaluate_frontier_need(
        user_text="복합",
        routed=_routed(RouteLane.CHAT_ONLY, route_analysis=analysis),
        ctx=DialogueContext(),
        router_mode=RouterMode.UNIFIED_ONLY,
    )
    assert not d.use_frontier
