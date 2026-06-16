"""Frontier 복합 요청 판별 — RouteAnalysis 구조 기반 (텍스트 휴리스틱 금지)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.assistant.route_analysis import (
    RouteAnalysis,
    has_dependent_operation_graph,
    is_complex_operation_graph,
)
from iris.assistant.router_policy import RouteLane, RoutedTurn
from iris.config.settings import RouterMode
from iris.core.context_manager import DialogueContext

SIMPLE_LANES = frozenset(
    {
        RouteLane.CHAT_ONLY,
        RouteLane.SEARCH,
        RouteLane.HYBRID,
        RouteLane.DIRECT_ACTION,
        RouteLane.FAST_TOOL,
        RouteLane.MULTI_TURN,
    }
)


@dataclass(frozen=True)
class FrontierDecision:
    use_frontier: bool
    reason: str
    signals: tuple[str, ...]
    confidence: float
    evidence: RouteAnalysis | None = None

    @classmethod
    def yes(
        cls,
        reason: str,
        *,
        evidence: RouteAnalysis | None = None,
        confidence: float = 0.85,
    ) -> FrontierDecision:
        return cls(
            use_frontier=True,
            reason=reason,
            signals=(reason,),
            confidence=confidence,
            evidence=evidence,
        )

    @classmethod
    def no(
        cls,
        reason: str,
        *,
        evidence: RouteAnalysis | None = None,
    ) -> FrontierDecision:
        return cls(
            use_frontier=False,
            reason=reason,
            signals=(),
            confidence=0.0,
            evidence=evidence,
        )


def _analysis_from_routed(routed: RoutedTurn) -> RouteAnalysis | None:
    return getattr(routed, "route_analysis", None)


def evaluate_frontier_need(
    *,
    user_text: str,
    routed: RoutedTurn,
    ctx: DialogueContext,
    complexity_threshold: float = 0.70,
    frontier_enabled: bool = True,
    router_mode: RouterMode | None = None,
) -> FrontierDecision:
    """
    Unified Router RouteAnalysis 기반 Frontier 필요 여부.
    user_text는 로깅·진단용 — 최종 판단에 키워드·접속사 검사하지 않음.
    """
    _ = user_text, ctx, complexity_threshold  # 진단·호환용

    if not frontier_enabled:
        return FrontierDecision.no("frontier_disabled")

    if router_mode is RouterMode.UNIFIED_ONLY:
        return FrontierDecision.no("unified_only")

    analysis = _analysis_from_routed(routed)

    if routed.lane is RouteLane.ORCHESTRATED:
        return FrontierDecision.yes("orchestrated_lane", evidence=analysis)

    if analysis is None or analysis.analysis_incomplete:
        return FrontierDecision.yes("incomplete_structured_analysis", evidence=analysis)

    if routed.requires_frontier:
        return FrontierDecision.yes("router_structured_decision", evidence=analysis)

    if has_dependent_operation_graph(analysis.operations):
        kinds = {op.kind.value for op in analysis.operations}
        if not kinds <= {"search", "respond"}:
            return FrontierDecision.yes("dependent_operation_graph", evidence=analysis)

    if analysis.requires_user_response and analysis.requires_execution:
        return FrontierDecision.yes("response_and_execution", evidence=analysis)

    if analysis.contains_cross_capability_flow:
        return FrontierDecision.yes("cross_capability_flow", evidence=analysis)

    if analysis.contains_conditional_flow or analysis.requires_monitoring:
        return FrontierDecision.yes("conditional_or_monitoring_flow", evidence=analysis)

    if is_complex_operation_graph(analysis):
        return FrontierDecision.yes("complex_operation_graph", evidence=analysis)

    if routed.lane in SIMPLE_LANES:
        return FrontierDecision.no("simple_structured_route", evidence=analysis)

    if routed.lane is RouteLane.COMPUTER_USE:
        return FrontierDecision.no("single_computer_use", evidence=analysis)

    return FrontierDecision.no("default_no_frontier", evidence=analysis)
