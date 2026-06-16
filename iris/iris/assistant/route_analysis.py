"""RouteAnalysis — Unified Router 구조화 출력 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

# 실행 Operation — 대화·검색·실행·검증 등 의미 단위
_EXECUTION_KINDS = frozenset(
    {
        "open",
        "create",
        "modify",
        "execute",
        "send",
        "monitor",
    }
)

_RESPOND_KIND = "respond"
_SEARCH_KIND = "search"


class OperationKind(str, Enum):
    RESPOND = "respond"
    SEARCH = "search"
    READ = "read"
    OPEN = "open"
    CREATE = "create"
    MODIFY = "modify"
    EXECUTE = "execute"
    VERIFY = "verify"
    MONITOR = "monitor"
    SEND = "send"
    ASK_USER = "ask_user"


class RouteAnalysisError(ValueError):
    """RouteAnalysis 파싱·검증 오류."""


@dataclass(frozen=True)
class RouteOperation:
    id: str
    kind: OperationKind
    goal: str
    capability: str | None
    target: str | None
    depends_on: tuple[str, ...] = ()
    conditional_on: str | None = None
    requires_verification: bool = False


@dataclass(frozen=True)
class RouteAnalysis:
    primary_goal: str
    operations: tuple[RouteOperation, ...]
    requires_user_response: bool
    requires_search: bool
    requires_execution: bool
    requires_monitoring: bool
    contains_conditional_flow: bool
    contains_cross_capability_flow: bool
    requested_capabilities: tuple[str, ...]
    confidence: float
    analysis_incomplete: bool = False
    consistency_errors: tuple[str, ...] = ()
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)


def _parse_operation_kind(raw: object) -> OperationKind:
    if not isinstance(raw, str) or not raw.strip():
        raise RouteAnalysisError("operation kind missing")
    key = raw.strip().lower()
    try:
        return OperationKind(key)
    except ValueError as exc:
        raise RouteAnalysisError(f"unknown operation kind: {raw!r}") from exc


def _parse_operations(raw: object) -> list[RouteOperation]:
    if not isinstance(raw, list):
        return []
    ops: list[RouteOperation] = []
    for item in raw:
        if not isinstance(item, dict):
            raise RouteAnalysisError("operation entry must be object")
        op_id = str(item.get("id") or "").strip()
        if not op_id:
            raise RouteAnalysisError("operation id required")
        kind = _parse_operation_kind(item.get("kind"))
        goal_raw = item.get("goal")
        goal = goal_raw.strip() if isinstance(goal_raw, str) else ""
        cap_raw = item.get("capability")
        capability = cap_raw.strip() if isinstance(cap_raw, str) and cap_raw.strip() else None
        target_raw = item.get("target")
        target = target_raw.strip() if isinstance(target_raw, str) and target_raw.strip() else None
        dep_raw = item.get("depends_on")
        depends: tuple[str, ...] = ()
        if isinstance(dep_raw, list):
            depends = tuple(str(x).strip() for x in dep_raw if str(x).strip())
        cond_raw = item.get("conditional_on")
        conditional_on = (
            cond_raw.strip() if isinstance(cond_raw, str) and cond_raw.strip() else None
        )
        requires_verification = bool(item.get("requires_verification", False))
        ops.append(
            RouteOperation(
                id=op_id,
                kind=kind,
                goal=goal,
                capability=capability,
                target=target,
                depends_on=depends,
                conditional_on=conditional_on,
                requires_verification=requires_verification,
            )
        )
    return ops


def _derive_flags_from_operations(
    operations: tuple[RouteOperation, ...],
) -> dict[str, bool]:
    kinds = {op.kind.value for op in operations}
    caps = {op.capability for op in operations if op.capability}
    has_conditional = any(op.conditional_on for op in operations)
    has_deps = any(op.depends_on for op in operations)
    cross_cap = len(caps) >= 2
    if not cross_cap and has_deps:
        # 의존 그래프가 있고 capability가 다르면 cross-capability
        cap_by_op = [op.capability for op in operations if op.capability]
        cross_cap = len(set(cap_by_op)) >= 2
    return {
        "requires_user_response": _RESPOND_KIND in kinds or OperationKind.ASK_USER.value in kinds,
        "requires_search": _SEARCH_KIND in kinds,
        "requires_execution": bool(kinds & _EXECUTION_KINDS),
        "requires_monitoring": OperationKind.MONITOR.value in kinds,
        "contains_conditional_flow": has_conditional,
        "contains_cross_capability_flow": cross_cap or (has_deps and len(operations) >= 2),
    }


def _validate_operation_graph(
    operations: tuple[RouteOperation, ...],
) -> list[str]:
    errors: list[str] = []
    ids = {op.id for op in operations}
    for op in operations:
        for dep in op.depends_on:
            if dep not in ids:
                errors.append(f"missing_dependency:{op.id}->{dep}")
        if op.kind in (
            OperationKind.OPEN,
            OperationKind.CREATE,
            OperationKind.MODIFY,
            OperationKind.EXECUTE,
            OperationKind.SEND,
        ) and not op.capability:
            errors.append(f"missing_capability:{op.id}")
        if op.conditional_on and op.conditional_on not in ids:
            errors.append(f"missing_conditional_ref:{op.id}->{op.conditional_on}")
    # 순환 의존 검사
    adj = {op.id: set(op.depends_on) for op in operations}
    visiting: set[str] = set()
    visited: set[str] = set()

    def _dfs(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for nxt in adj.get(node, ()):
            if _dfs(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for op_id in ids:
        if _dfs(op_id):
            errors.append(f"dependency_cycle:{op_id}")
            break
    return errors


def _bool_field(raw: Mapping[str, Any], key: str, default: bool = False) -> bool:
    val = raw.get(key)
    if val is None:
        return default
    return bool(val)


def _capabilities_from_operations(
    operations: tuple[RouteOperation, ...],
) -> tuple[str, ...]:
    caps = sorted({op.capability for op in operations if op.capability})
    return tuple(caps)


def build_route_analysis_from_router_json(
    raw: Mapping[str, Any],
    *,
    primary_goal: str,
    confidence: float,
) -> RouteAnalysis:
    """Unified Router JSON → RouteAnalysis (operations 있으면 파싱, 없으면 레거시 어댑터)."""
    try:
        parsed_ops = _parse_operations(raw.get("operations"))
    except RouteAnalysisError as exc:
        return RouteAnalysis(
            primary_goal=primary_goal,
            operations=(),
            requires_user_response=False,
            requires_search=False,
            requires_execution=False,
            requires_monitoring=False,
            contains_conditional_flow=False,
            contains_cross_capability_flow=False,
            requested_capabilities=(),
            confidence=confidence,
            analysis_incomplete=True,
            consistency_errors=(str(exc),),
            raw_metadata={"source": "parse_error"},
        )

    if parsed_ops:
        operations = tuple(parsed_ops)
        derived = _derive_flags_from_operations(operations)
        declared = {
            "requires_user_response": _bool_field(raw, "requires_user_response"),
            "requires_search": _bool_field(raw, "requires_search"),
            "requires_execution": _bool_field(raw, "requires_execution"),
            "requires_monitoring": _bool_field(raw, "requires_monitoring"),
            "contains_conditional_flow": _bool_field(raw, "contains_conditional_flow"),
            "contains_cross_capability_flow": _bool_field(
                raw, "contains_cross_capability_flow"
            ),
        }
        errors = _validate_operation_graph(operations)
        for key, derived_val in derived.items():
            if key in declared and declared[key] != derived_val:
                errors.append(f"flag_mismatch:{key}")
        caps_raw = raw.get("requested_capabilities")
        requested: tuple[str, ...]
        if isinstance(caps_raw, list) and caps_raw:
            requested = tuple(str(x).strip() for x in caps_raw if str(x).strip())
        else:
            requested = _capabilities_from_operations(operations)
        if requested and _capabilities_from_operations(operations):
            op_caps = set(_capabilities_from_operations(operations))
            if set(requested) != op_caps and not op_caps.issubset(set(requested)):
                errors.append("capability_list_mismatch")
        incomplete = bool(errors) or bool(raw.get("analysis_incomplete"))
        return RouteAnalysis(
            primary_goal=primary_goal,
            operations=operations,
            requires_user_response=derived["requires_user_response"],
            requires_search=derived["requires_search"],
            requires_execution=derived["requires_execution"],
            requires_monitoring=derived["requires_monitoring"],
            contains_conditional_flow=derived["contains_conditional_flow"],
            contains_cross_capability_flow=derived["contains_cross_capability_flow"],
            requested_capabilities=requested or _capabilities_from_operations(operations),
            confidence=confidence,
            analysis_incomplete=incomplete,
            consistency_errors=tuple(errors),
            raw_metadata={"source": "structured"},
        )

    # 레거시 — lane/intent 메타만으로 최소 operation 구성 (user_text 키워드 금지)
    return adapt_legacy_route_metadata(
        intent=str(raw.get("intent") or ""),
        lane=str(raw.get("lane") or ""),
        task_type=str(raw.get("task_type") or "") if raw.get("task_type") else None,
        slots=raw.get("slots") if isinstance(raw.get("slots"), dict) else {},
        primary_goal=primary_goal,
        confidence=confidence,
        requires_frontier=bool(raw.get("requires_frontier", False)),
        complexity=str(raw.get("complexity") or ""),
    )


def adapt_legacy_route_metadata(
    *,
    intent: str,
    lane: str,
    task_type: str | None,
    slots: Mapping[str, Any],
    primary_goal: str,
    confidence: float,
    requires_frontier: bool = False,
    complexity: str = "",
) -> RouteAnalysis:
    """구 Unified JSON — lane·intent·slots 메타만으로 단일/단순 operation 생성."""
    intent_l = intent.strip().lower()
    lane_l = lane.strip().lower()
    ops: list[RouteOperation] = []

    if lane_l in ("chat_only",) or intent_l == "chat":
        ops.append(
            RouteOperation(
                id="op-1",
                kind=OperationKind.RESPOND,
                goal=primary_goal,
                capability=None,
                target=None,
            )
        )
    elif lane_l in ("search", "hybrid") or intent_l == "search":
        ops.append(
            RouteOperation(
                id="op-1",
                kind=OperationKind.SEARCH,
                goal=primary_goal,
                capability="web.search",
                target=str(slots.get("query") or slots.get("search_query") or ""),
            )
        )
        ops.append(
            RouteOperation(
                id="op-2",
                kind=OperationKind.RESPOND,
                goal="검색 결과를 바탕으로 답변한다",
                capability=None,
                target=None,
                depends_on=("op-1",),
            )
        )
    elif intent_l == "launch_app" or task_type == "open_app":
        app_key = str(slots.get("app_key") or "")
        ops.append(
            RouteOperation(
                id="op-1",
                kind=OperationKind.OPEN,
                goal=primary_goal,
                capability="app.launch",
                target=app_key or None,
            )
        )
    elif lane_l == "fast_tool" or intent_l == "fast_tool":
        ops.append(
            RouteOperation(
                id="op-1",
                kind=OperationKind.READ,
                goal=primary_goal,
                capability="system.info",
                target=None,
            )
        )
    elif intent_l in ("work_mode", "game_mode", "creative_mode") or lane_l == "multi_turn":
        ops.append(
            RouteOperation(
                id="op-1",
                kind=OperationKind.ASK_USER,
                goal=primary_goal,
                capability="mode.dialogue",
                target=intent_l or lane_l,
            )
        )
    elif lane_l in ("direct_action", "computer_use", "orchestrated") or intent_l in (
        "computer_use",
        "orchestrated",
    ):
        cap = "computer.use"
        if task_type:
            cap = f"task.{task_type}"
        ops.append(
            RouteOperation(
                id="op-1",
                kind=OperationKind.EXECUTE,
                goal=primary_goal,
                capability=cap,
                target=str(slots.get("app_key") or slots.get("url") or "") or None,
            )
        )
    else:
        return RouteAnalysis(
            primary_goal=primary_goal,
            operations=(),
            requires_user_response=False,
            requires_search=False,
            requires_execution=False,
            requires_monitoring=False,
            contains_conditional_flow=False,
            contains_cross_capability_flow=False,
            requested_capabilities=(),
            confidence=confidence,
            analysis_incomplete=True,
            consistency_errors=("legacy_metadata_insufficient",),
            raw_metadata={"source": "legacy_incomplete"},
        )

    operations = tuple(ops)
    derived = _derive_flags_from_operations(operations)
    incomplete = requires_frontier and complexity == "complex" and len(operations) < 2
    return RouteAnalysis(
        primary_goal=primary_goal,
        operations=operations,
        requires_user_response=derived["requires_user_response"],
        requires_search=derived["requires_search"],
        requires_execution=derived["requires_execution"],
        requires_monitoring=derived["requires_monitoring"],
        contains_conditional_flow=derived["contains_conditional_flow"],
        contains_cross_capability_flow=derived["contains_cross_capability_flow"],
        requested_capabilities=_capabilities_from_operations(operations),
        confidence=confidence,
        analysis_incomplete=incomplete,
        raw_metadata={"source": "legacy_adapter"},
    )


def has_dependent_operation_graph(operations: tuple[RouteOperation, ...]) -> bool:
    """의존 관계가 있는 operation 그래프."""
    if len(operations) < 2:
        return False
    return any(op.depends_on for op in operations)


def is_complex_operation_graph(analysis: RouteAnalysis) -> bool:
    """복합 요청 — 단순 작업 수가 아니라 capability·의존·조건 흐름 기준."""
    if analysis.analysis_incomplete:
        return True
    if analysis.contains_cross_capability_flow:
        return True
    if analysis.contains_conditional_flow or analysis.requires_monitoring:
        return True
    if analysis.requires_user_response and analysis.requires_execution:
        return True
    if has_dependent_operation_graph(analysis.operations):
        # 단일 검색→응답은 depends 있어도 단순
        kinds = {op.kind for op in analysis.operations}
        if kinds <= {OperationKind.SEARCH, OperationKind.RESPOND}:
            return False
        return True
    return False
