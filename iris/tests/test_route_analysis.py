"""RouteAnalysis 파서·계약 테스트."""

from __future__ import annotations

import pytest

from iris.assistant.route_analysis import (
    OperationKind,
    RouteAnalysisError,
    RouteOperation,
    adapt_legacy_route_metadata,
    build_route_analysis_from_router_json,
    has_dependent_operation_graph,
)
from iris.assistant.unified_router import parse_unified_route_json


def _op(
    op_id: str,
    kind: str,
    goal: str = "g",
    capability: str | None = None,
    depends_on: list[str] | None = None,
) -> dict:
    return {
        "id": op_id,
        "kind": kind,
        "goal": goal,
        "capability": capability,
        "target": None,
        "depends_on": depends_on or [],
        "conditional_on": None,
        "requires_verification": False,
    }


def test_router_returns_operations() -> None:
    raw = {
        "intent": "chat",
        "lane": "chat_only",
        "goal": "설명",
        "operations": [_op("op-1", "respond", "FastAPI 설명")],
        "requires_user_response": True,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "FastAPI 설명")
    assert payload is not None
    assert payload.route_analysis is not None
    assert len(payload.route_analysis.operations) == 1
    assert payload.route_analysis.operations[0].kind is OperationKind.RESPOND


def test_router_returns_capabilities() -> None:
    raw = {
        "intent": "orchestrated",
        "lane": "orchestrated",
        "goal": "작업",
        "operations": [
            _op("op-1", "read", "분석", "project.analyze"),
            _op("op-2", "modify", "수정", "filesystem.write", ["op-1"]),
        ],
        "requested_capabilities": ["project.analyze", "filesystem.write"],
        "contains_cross_capability_flow": True,
        "requires_execution": True,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "작업")
    assert payload is not None
    assert payload.route_analysis is not None
    caps = payload.route_analysis.requested_capabilities
    assert "project.analyze" in caps
    assert "filesystem.write" in caps


def test_router_returns_dependencies() -> None:
    raw = {
        "intent": "orchestrated",
        "lane": "orchestrated",
        "goal": "빌드",
        "operations": [
            _op("op-1", "modify", "수정", "fs.write"),
            _op("op-2", "execute", "빌드", "project.build", ["op-1"]),
        ],
        "requires_execution": True,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "빌드")
    assert payload is not None
    assert payload.route_analysis is not None
    assert has_dependent_operation_graph(payload.route_analysis.operations)


def test_router_marks_conditional_flow() -> None:
    raw = {
        "intent": "computer_use",
        "lane": "computer_use",
        "goal": "모니터",
        "operations": [
            {
                **_op("op-1", "monitor", "상태 확인", "task.monitor"),
                "conditional_on": None,
            },
            {
                **_op("op-2", "execute", "재실행", "task.retry", ["op-1"]),
                "conditional_on": "op-1",
            },
        ],
        "contains_conditional_flow": True,
        "requires_monitoring": True,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "모니터")
    assert payload is not None
    assert payload.route_analysis is not None
    assert payload.route_analysis.contains_conditional_flow


def test_router_detects_cross_capability_flow() -> None:
    raw = {
        "intent": "orchestrated",
        "lane": "orchestrated",
        "goal": "정리",
        "operations": [
            _op("op-1", "search", "뉴스", "web.search"),
            _op("op-2", "create", "문서", "doc.write", ["op-1"]),
        ],
        "contains_cross_capability_flow": True,
        "requires_search": True,
        "requires_execution": True,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "정리")
    assert payload is not None
    assert payload.route_analysis is not None
    assert payload.route_analysis.contains_cross_capability_flow


def test_router_rejects_unknown_operation_kind() -> None:
    raw = {
        "intent": "chat",
        "lane": "chat_only",
        "goal": "x",
        "operations": [_op("op-1", "fly_to_moon")],
        "confidence": 0.9,
    }
    analysis = build_route_analysis_from_router_json(raw, primary_goal="x", confidence=0.9)
    assert analysis.analysis_incomplete


def test_router_rejects_missing_dependency() -> None:
    raw = {
        "intent": "orchestrated",
        "lane": "orchestrated",
        "goal": "x",
        "operations": [_op("op-2", "execute", "빌드", "project.build", ["op-missing"])],
        "requires_execution": True,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "x")
    assert payload is not None
    assert payload.route_analysis is not None
    assert payload.route_analysis.analysis_incomplete
    assert any("missing_dependency" in e for e in payload.route_analysis.consistency_errors)


def test_router_rejects_dependency_cycle() -> None:
    raw = {
        "intent": "orchestrated",
        "lane": "orchestrated",
        "goal": "x",
        "operations": [
            _op("op-1", "read", "a", "a.cap", ["op-2"]),
            _op("op-2", "modify", "b", "b.cap", ["op-1"]),
        ],
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "x")
    assert payload is not None
    assert payload.route_analysis is not None
    assert any("dependency_cycle" in e for e in payload.route_analysis.consistency_errors)


def test_router_detects_execution_flag_mismatch() -> None:
    raw = {
        "intent": "chat",
        "lane": "chat_only",
        "goal": "x",
        "operations": [_op("op-1", "execute", "실행", "cu.run")],
        "requires_execution": False,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "x")
    assert payload is not None
    assert payload.route_analysis is not None
    assert any("flag_mismatch" in e for e in payload.route_analysis.consistency_errors)


def test_legacy_route_is_adapted_without_text_guessing() -> None:
    analysis = adapt_legacy_route_metadata(
        intent="chat",
        lane="chat_only",
        task_type=None,
        slots={},
        primary_goal="인사",
        confidence=0.9,
    )
    assert len(analysis.operations) == 1
    assert analysis.operations[0].kind is OperationKind.RESPOND
    assert not analysis.analysis_incomplete
