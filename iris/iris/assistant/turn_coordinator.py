"""TurnCoordinator — 한 턴 Router·Dialogue·Planner·Executor 결과 병합."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from iris.assistant.dialogue_agent import DialogueAgent
from iris.assistant.frontier_agent import run_frontier_turn
from iris.assistant.computer_use_agent import extract_user_question
from iris.assistant.llm_approval import FollowupDecision, resolve_followup_for_pending
from iris.assistant.llm_intent_router import route_with_llm
from iris.assistant.unified_router import route_user_turn
from iris.assistant.orchestrator import AgentOrchestrator
from iris.assistant.router_policy import (
    RouteLane,
    RoutedTurn,
    is_multi_turn_active,
    resolve_route_lane,
)
from iris.assistant.safety_guard import quick_block_user_text
from iris.core.activity_sink import push_activity_line
from iris.core.command_router import CommandKind
from iris.core.context_manager import DialogueStep, PendingComputerUseGoal
if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient


def _search_slot_query(routed: RoutedTurn) -> str | None:
    """Phase 3 — 라우터가 넣은 웹 검색 질의(slots.query)."""
    raw = routed.slots.get("query")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _search_slot_queries(routed: RoutedTurn) -> list[str]:
    """비교 등 — slots.queries 추가 검색어."""
    raw = routed.slots.get("queries")
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _search_answer_shape(routed: RoutedTurn) -> str | None:
    raw = routed.slots.get("answer_shape")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return None


def _build_search_delegate_meta(routed: RoutedTurn, *, hybrid: bool) -> str:
    """SearchWorker·UI에 전달할 JSON 메타."""
    meta: dict[str, Any] = {
        "hybrid": hybrid,
        "queries": _search_slot_queries(routed),
        "answer_shape": _search_answer_shape(routed) or "",
        "knowledge_lane": routed.knowledge_lane or "",
    }
    return json.dumps(meta, ensure_ascii=False)


@dataclass
class TurnResult:
    """한 턴 처리 결과."""

    turn_id: str
    route: str
    user_visible: str
    early_ack: str | None
    executed: bool
    spoken_followup: str | None = None  # TTS용 — ack 제외 실행 결과만
    logs: list[str] = field(default_factory=list)
    delegate_search: bool = False
    delegate_dialogue_stream: bool = False
    delegate_frontier_stream: bool = False
    frontier_reply: str = ""
    search_intent_name: str | None = None
    # Phase 3: 라우터 slots.query → 웹 리서치 기본 검색어 (비어 있으면 기존 추출 로직)
    search_query: str | None = None
    search_meta_json: str = ""  # hybrid·queries·answer_shape
    store_history: bool = False

    @property
    def had_early_ack(self) -> bool:
        return self.early_ack is not None


def _phase3_preset_llm_enabled(assistant: IrisAssistant) -> bool:
    """멀티턴 프리셋 후보를 LLM이 고를지 (.env IRIS_PHASE3_MODE_PRESET_LLM)."""
    settings = assistant._settings
    if settings is None:
        return True
    return bool(getattr(settings, "phase3_mode_preset_llm", True))


class TurnCoordinator:
    """DialogueContext·memory·로그 갱신은 Coordinator만 수행 (경쟁 방지)."""

    def __init__(self, assistant: IrisAssistant, gemma: GemmaClient) -> None:
        self._assistant = assistant
        self._gemma = gemma
        self._dialogue = DialogueAgent(assistant, gemma)

    def run_turn(
        self,
        user_text: str,
        *,
        routed: CommandKind | None = None,
        on_early_ack: Callable[[str], None] | None = None,
        on_frontier_reply: Callable[[str], None] | None = None,
        on_user_notify: Callable[[str], None] | None = None,
    ) -> TurnResult:
        turn_id = uuid.uuid4().hex[:12]
        logs: list[str] = []

        push_activity_line(f"TurnCoordinator: pipeline started turn_id={turn_id}.")

        block = quick_block_user_text(user_text)
        if block:
            push_activity_line("TurnCoordinator: safety guard blocked input.")
            self._assistant._db.insert_log("safety", "blocked", block)
            return TurnResult(
                turn_id=turn_id,
                route=RouteLane.CHAT_ONLY.value,
                user_visible=f"Iris: {block}",
                early_ack=None,
                executed=False,
                logs=["safety_block"],
            )

        ctx = self._assistant.ctx
        pending_cu = ctx.pending_cu
        if pending_cu is not None:
            cu_result = self._handle_pending_cu_followup(
                turn_id, user_text, pending_cu, logs
            )
            if cu_result is not None:
                return cu_result

        frontier_spoke = False
        frontier_reply = ""

        # --- Frontier 1회 envelope (멀티턴·pending_cu 제외) ---
        if _frontier_enabled(self._assistant) and not is_multi_turn_active(ctx):
            frontier = run_frontier_turn(
                user_text, ctx, self._gemma, assistant=self._assistant
            )
            if frontier is not None:
                logs.extend(frontier.logs)
                frontier_reply = frontier.user_reply
                # CHAT_ONLY는 delegate_frontier_stream 1회만 — prefetch 콜백 시 UI 이중 재생
                if (
                    frontier.needs_execution
                    and on_frontier_reply is not None
                    and frontier_reply
                ):
                    on_frontier_reply(frontier_reply)
                    logs.append("frontier_reply_callback")
                    frontier_spoke = True
                if not frontier.needs_execution:
                    lane = frontier.routed_turn.lane
                    if lane is RouteLane.CHAT_ONLY:
                        push_activity_line(
                            "Frontier: CHAT_ONLY — single LLM, no unified router."
                        )
                        return TurnResult(
                            turn_id=turn_id,
                            route=RouteLane.CHAT_ONLY.value,
                            user_visible="",
                            early_ack=None,
                            executed=False,
                            logs=logs + ["frontier_chat_only"],
                            delegate_frontier_stream=True,
                            frontier_reply=frontier_reply,
                            store_history=True,
                        )
                    push_activity_line(
                        f"Frontier: knowledge delegate lane={lane.value}."
                    )
                    return self._dispatch_routed_turn(
                        turn_id,
                        user_text,
                        frontier.routed_turn,
                        logs,
                        on_early_ack=on_early_ack,
                        on_user_notify=on_user_notify,
                        frontier_spoke=False,
                        frontier_reply=frontier_reply,
                    )
                return self._dispatch_routed_turn(
                    turn_id,
                    user_text,
                    frontier.routed_turn,
                    logs,
                    on_early_ack=on_early_ack,
                    on_user_notify=on_user_notify,
                    frontier_spoke=frontier_spoke,
                    frontier_reply=frontier_reply,
                )

        # --- 폴백 라우팅: Unified LLM Router (regex fast path 제거) ---
        routed_turn: RoutedTurn
        if _unified_llm_router_enabled(self._assistant):
            routed_turn = route_user_turn(
                user_text, ctx, self._gemma, assistant=self._assistant
            )
        elif _llm_intent_router_enabled(self._assistant):
            fb = routed if routed is not None else CommandKind.GENERAL_CHAT
            routed_turn = route_with_llm(
                user_text, ctx, self._gemma, fallback_kind=fb
            )
        else:
            push_activity_line(
                "Router: LLM routers disabled — chat_only safe fallback."
            )
            logs.append("router_llm_disabled")
            routed_turn = RoutedTurn(
                kind=CommandKind.GENERAL_CHAT,
                lane=RouteLane.CHAT_ONLY,
            )
        return self._dispatch_routed_turn(
            turn_id,
            user_text,
            routed_turn,
            logs,
            on_early_ack=on_early_ack,
            on_user_notify=on_user_notify,
            frontier_spoke=False,
            frontier_reply="",
        )

    def _dispatch_routed_turn(
        self,
        turn_id: str,
        user_text: str,
        routed_turn: RoutedTurn,
        logs: list[str],
        *,
        on_early_ack: Callable[[str], None] | None = None,
        on_user_notify: Callable[[str], None] | None = None,
        frontier_spoke: bool = False,
        frontier_reply: str = "",
    ) -> TurnResult:
        ctx = self._assistant.ctx
        lane = routed_turn.lane
        kind = routed_turn.kind
        logs.append(f"lane={lane.value} kind={kind.name}")
        push_activity_line(f"Router: lane={lane.value} intent={kind.name}.")

        if routed_turn.needs_user_confirm:
            confirm_msg = (
                routed_turn.clarification
                or "이 작업은 확인이 필요합니다. 진행할까요?"
            )
            cu_goal = (routed_turn.goal or user_text).strip()
            ctx.pending_cu = PendingComputerUseGoal(
                goal=cu_goal,
                risk_hint=routed_turn.risk_hint,
                prompt=confirm_msg,
                slots=dict(routed_turn.slots),
            )
            push_activity_line("Router: computer-use confirmation required — pending_cu set.")
            return TurnResult(
                turn_id=turn_id,
                route=lane.value,
                user_visible=f"Iris: {confirm_msg}",
                early_ack=None,
                executed=False,
                logs=logs + ["needs_user_confirm", "pending_cu_set"],
                store_history=True,
            )

        self._assistant._db.insert_log(
            "turn_coordinator",
            lane.value,
            f"{turn_id} {kind.name}",
        )
        push_activity_line(f"DB: turn_coordinator log lane={lane.value}.")

        if lane is RouteLane.SEARCH:
            slot_q = _search_slot_query(routed_turn)
            push_activity_line("Lane SEARCH: delegating to web research worker.")
            return TurnResult(
                turn_id=turn_id,
                route=lane.value,
                user_visible="",
                early_ack=None,
                executed=False,
                logs=logs,
                delegate_search=True,
                search_intent_name=kind.name,
                search_query=slot_q,
                search_meta_json=_build_search_delegate_meta(routed_turn, hybrid=False),
            )

        if lane is RouteLane.HYBRID:
            slot_q = _search_slot_query(routed_turn)
            push_activity_line("Lane HYBRID: search then LLM with hybrid prompt.")
            return TurnResult(
                turn_id=turn_id,
                route=lane.value,
                user_visible="",
                early_ack=None,
                executed=False,
                logs=logs,
                delegate_search=True,
                search_intent_name=kind.name,
                search_query=slot_q,
                search_meta_json=_build_search_delegate_meta(routed_turn, hybrid=True),
            )

        if lane is RouteLane.CHAT_ONLY:
            push_activity_line(
                "Lane CHAT_ONLY: delegate streaming dialogue to UI."
            )
            logs.append("dialogue_stream_delegate")
            return TurnResult(
                turn_id=turn_id,
                route=lane.value,
                user_visible="",
                early_ack=None,
                executed=False,
                logs=logs,
                delegate_dialogue_stream=True,
                store_history=True,
            )

        if lane is RouteLane.MULTI_TURN:
            push_activity_line("Lane MULTI_TURN: mode / preset flow.")
            preset_id_hint: str | None = None
            if _phase3_preset_llm_enabled(self._assistant) and ctx.step in (
                DialogueStep.WORK_ASK_TASK,
                DialogueStep.GAME_ASK_TITLE,
                DialogueStep.CREATIVE_ASK_TYPE,
            ):
                from iris.assistant.mode_preset_resolver import resolve_mode_preset_id_llm

                mode_key = {
                    DialogueStep.WORK_ASK_TASK: "work",
                    DialogueStep.GAME_ASK_TITLE: "game",
                    DialogueStep.CREATIVE_ASK_TYPE: "creative",
                }.get(ctx.step)
                if mode_key is not None:
                    preset_id_hint = resolve_mode_preset_id_llm(
                        user_text, mode_key, self._gemma  # type: ignore[arg-type]
                    )
            reply = self._assistant.handle_user_text(
                user_text, routed=kind, llm_preset_id=preset_id_hint
            )
            if not reply:
                reply = "Iris: 이어서 말씀해 주세요."
            return TurnResult(
                turn_id=turn_id,
                route=lane.value,
                user_visible=reply,
                early_ack=None,
                executed=bool(reply),
                logs=logs + ["multi_turn"],
            )

        if lane is RouteLane.COMPUTER_USE:
            push_activity_line("Lane COMPUTER_USE: starting PAV loop path.")
            return self._run_computer_use(
                turn_id,
                user_text,
                routed_turn,
                logs,
                on_early_ack=on_early_ack,
                on_user_notify=on_user_notify,
                frontier_spoke=frontier_spoke,
                frontier_reply=frontier_reply,
            )

        if lane is RouteLane.FAST_TOOL:
            push_activity_line("Lane FAST_TOOL: single Tier-1 tool.")
            return self._run_fast_tool(
                turn_id,
                user_text,
                routed_turn,
                logs,
                on_early_ack=on_early_ack,
                frontier_spoke=frontier_spoke,
                frontier_reply=frontier_reply,
            )

        if lane is RouteLane.DIRECT_ACTION:
            push_activity_line("Lane DIRECT_ACTION: fast execute with early ack.")
            return self._run_direct_action(
                turn_id,
                user_text,
                routed_turn,
                logs,
                on_early_ack=on_early_ack,
                frontier_spoke=frontier_spoke,
                frontier_reply=frontier_reply,
            )

        # ORCHESTRATED — 기존 AgentOrchestrator (Planner 포함)
        push_activity_line("Lane ORCHESTRATED: planner + agent loop.")
        return self._run_orchestrated(turn_id, user_text, routed_turn.kind, logs)

    def _handle_pending_cu_followup(
        self,
        turn_id: str,
        user_text: str,
        pending: PendingComputerUseGoal,
        logs: list[str],
    ) -> TurnResult | None:
        """pending_cu 후속 — approve 시 대기 스텝 1회 또는 CU 재호출, unrelated면 pending 해제."""
        llm_on = _llm_approval_enabled(self._assistant)
        cls = resolve_followup_for_pending(
            user_text,
            pending.prompt or pending.goal,
            self._gemma,
            force_rule_only=not llm_on,
            use_llm=llm_on,
        )
        logs.append(f"pending_cu_followup={cls.decision.value}")

        if cls.decision is FollowupDecision.REJECT:
            push_activity_line("CU follow-up: user rejected pending action.")
            self._assistant.ctx.clear_pending_cu()
            return TurnResult(
                turn_id=turn_id,
                route=RouteLane.COMPUTER_USE.value,
                user_visible="Iris: 작업을 취소했습니다.",
                early_ack=None,
                executed=False,
                logs=logs + ["pending_cu_reject"],
                store_history=True,
            )

        if cls.decision is FollowupDecision.CLARIFY:
            push_activity_line("CU follow-up: clarification requested.")
            hint = pending.prompt or "진행할까요? ('진행해줘' / '취소')"
            return TurnResult(
                turn_id=turn_id,
                route=RouteLane.COMPUTER_USE.value,
                user_visible=f"Iris: {hint}",
                early_ack=None,
                executed=False,
                logs=logs + ["pending_cu_clarify"],
                store_history=True,
            )

        if cls.decision is FollowupDecision.UNRELATED:
            push_activity_line("CU follow-up: unrelated input — clearing pending_cu.")
            self._assistant.ctx.clear_pending_cu()
            logs.append("pending_cu_cleared_unrelated")
            return None

        if cls.decision is not FollowupDecision.APPROVE:
            return None

        # CRITICAL 대기 스텝: 승인 후 CU 루프 재개 (full_plan ctx 복원·checkpoint verify·계속)
        if pending.has_pending_tool:
            push_activity_line(
                f"CU follow-up: approved pending tool={pending.pending_tool_name!r} — resuming loop."
            )
            goal = pending.goal
            slots = dict(pending.slots)
            risk_hint = pending.risk_hint
            resume_pending = PendingComputerUseGoal(
                goal=goal,
                risk_hint=risk_hint,
                prompt=pending.prompt,
                slots=slots,
                pending_tool_name=pending.pending_tool_name,
                pending_tool_params=dict(pending.pending_tool_params),
                pending_tool_preview=pending.pending_tool_preview,
                cu_mode=pending.cu_mode,
                executed_through_index=pending.executed_through_index,
                pending_plan_index=pending.pending_plan_index,
                pending_checkpoint_id=pending.pending_checkpoint_id,
                plan_id=pending.plan_id,
                full_plan_snapshot=dict(pending.full_plan_snapshot),
                cu_observations=list(pending.cu_observations),
            )
            self._assistant.ctx.clear_pending_cu()
            reply = self._assistant.run_computer_use_resume(resume_pending)
            user_visible, executed, extra_logs = _finalize_cu_reply(
                self._assistant.ctx,
                goal=goal,
                slots=slots,
                reply=reply,
                risk_hint=risk_hint,
            )
            logs.extend(extra_logs)
            logs.append("pending_cu_resume_loop")
            if not user_visible.startswith("Iris:"):
                user_visible = f"Iris: {user_visible}"
            return TurnResult(
                turn_id=turn_id,
                route=RouteLane.COMPUTER_USE.value,
                user_visible=user_visible,
                early_ack=None,
                executed=executed,
                logs=logs + ["pending_cu_approved"],
                store_history=True,
            )

        goal = pending.goal
        slots = dict(pending.slots)
        self._assistant.ctx.clear_pending_cu()
        push_activity_line("CU follow-up: approved — resuming PAV loop.")
        reply = self._assistant.run_computer_use_loop(
            user_text,
            goal=goal,
            slots=slots or None,
            on_user_notify=None,
        )
        user_visible, executed, extra_logs = _finalize_cu_reply(
            self._assistant.ctx,
            goal=goal,
            slots=slots,
            reply=reply,
            risk_hint=pending.risk_hint,
        )
        logs.extend(extra_logs)
        if not user_visible.startswith("Iris:"):
            user_visible = f"Iris: {user_visible}"
        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.COMPUTER_USE.value,
            user_visible=user_visible,
            early_ack=None,
            executed=executed,
            logs=logs + ["pending_cu_approved"],
            store_history=True,
        )

    def _run_computer_use(
        self,
        turn_id: str,
        user_text: str,
        routed_turn: RoutedTurn,
        logs: list[str],
        *,
        on_early_ack: Callable[[str], None] | None = None,
        on_user_notify: Callable[[str], None] | None = None,
        frontier_spoke: bool = False,
        frontier_reply: str = "",
    ) -> TurnResult:
        """CU 레인 — early_ack 후 goal/slots로 PAV 루프 (ORCHESTRATED ≠ PC 미디어 스킬)."""
        ctx = self._assistant.ctx
        cu_goal = (routed_turn.goal or user_text).strip()
        slots = dict(routed_turn.slots)
        if routed_turn.task_type:
            slots.setdefault("task_type", routed_turn.task_type)
        if frontier_spoke:
            ack = ""
            had_early = True
            logs.append("cu_ack_skipped_frontier")
        else:
            ack = self._dialogue.cu_early_ack(cu_goal, slots)
            had_early = on_early_ack is not None
            logs.append(f"cu_ack={ack[:40]}")
            if on_early_ack is not None:
                on_early_ack(ack)
            logs.append("early_ack_callback")

        raw_reply = self._assistant.run_computer_use_loop(
            user_text,
            goal=cu_goal,
            slots=slots or None,
            routed=routed_turn.kind,
            on_user_notify=on_user_notify,
        )
        user_visible, executed, extra_logs = _finalize_cu_reply(
            ctx,
            goal=cu_goal,
            slots=slots,
            reply=raw_reply,
            risk_hint=routed_turn.risk_hint,
        )
        logs.extend(extra_logs)
        exec_reply = user_visible
        merge_ack = frontier_reply if frontier_spoke else ack
        user_visible = build_user_visible(merge_ack, exec_reply, had_early_ack=had_early)
        spoken_followup = build_spoken_followup(merge_ack, exec_reply, had_early_ack=had_early)
        logs.append("computer_use")
        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.COMPUTER_USE.value,
            user_visible=user_visible,
            early_ack=merge_ack or None,
            spoken_followup=spoken_followup,
            executed=executed,
            logs=logs,
            store_history=True,
        )

    def _run_direct_action(
        self,
        turn_id: str,
        user_text: str,
        routed: RoutedTurn,
        logs: list[str],
        *,
        on_early_ack: Callable[[str], None] | None = None,
        frontier_spoke: bool = False,
        frontier_reply: str = "",
    ) -> TurnResult:
        """ack → (콜백) → 실행(handle_user_text / open_url) → 병합 메시지."""
        kind = routed.kind
        slots = dict(routed.slots)
        if frontier_spoke:
            ack = ""
            had_early = True
            logs.append("ack_skipped_frontier")
        else:
            ack = self._dialogue.ack(user_text, kind, slots=slots or None)
            logs.append(f"ack={ack[:40]}")
            had_early = on_early_ack is not None
            if on_early_ack is not None:
                on_early_ack(ack)
            logs.append("early_ack_callback")

        exec_reply = ""
        executed = False

        app_key = str(slots.get("app_key") or "").strip()
        if kind is CommandKind.APP_LAUNCH and app_key:
            exec_reply = self._assistant.launch_app_by_key(
                app_key,
                display_name=str(slots.get("display_name") or ""),
                user_text=user_text,
            )
            executed = bool(exec_reply)
            logs.append("launch_app_slots")
        elif routed.open_url:
            exec_reply = self._assistant.request_automation_tool(
                "open_url",
                {"url": routed.open_url},
                f"URL 열기: {routed.open_url}",
            )
            executed = True
            logs.append("open_url")
        else:
            exec_reply = self._assistant.handle_user_text(user_text, routed=kind)
            if exec_reply:
                executed = True
                logs.append("handle_user_text")

        merge_ack = frontier_reply if frontier_spoke else ack
        user_visible = build_user_visible(merge_ack, exec_reply, had_early_ack=had_early)
        spoken_followup = build_spoken_followup(merge_ack, exec_reply, had_early_ack=had_early)
        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.DIRECT_ACTION.value,
            user_visible=user_visible,
            early_ack=merge_ack or None,
            spoken_followup=spoken_followup,
            executed=executed,
            logs=logs,
            store_history=False,
        )

    def _run_fast_tool(
        self,
        turn_id: str,
        user_text: str,
        routed: RoutedTurn,
        logs: list[str],
        *,
        on_early_ack: Callable[[str], None] | None = None,
        frontier_spoke: bool = False,
        frontier_reply: str = "",
    ) -> TurnResult:
        """Tier 1 전용 도구 1스텝 (Computer Use 루프 생략)."""
        kind = routed.kind
        if frontier_spoke:
            ack = ""
            had_early = True
            logs.append("fast_ack_skipped_frontier")
        else:
            ack = self._dialogue.ack(user_text, kind)
            logs.append(f"fast_ack={ack[:40]}")
            had_early = on_early_ack is not None
            if on_early_ack is not None:
                on_early_ack(ack)
            logs.append("early_ack_callback")

        exec_reply = ""
        executed = False

        if kind is CommandKind.GET_SYSTEM_INFO:
            exec_reply = self._assistant.request_automation_tool(
                "get_system_info",
                {},
                "시스템 사양·리소스 요약",
                settings=self._assistant._settings,
            )
            executed = True
            logs.append("get_system_info")
        else:
            logs.append(f"fast_tool_unhandled:{kind.name}")

        merge_ack = frontier_reply if frontier_spoke else ack
        user_visible = build_user_visible(merge_ack, exec_reply, had_early_ack=had_early)
        spoken_followup = build_spoken_followup(merge_ack, exec_reply, had_early_ack=had_early)

        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.FAST_TOOL.value,
            user_visible=user_visible,
            early_ack=merge_ack or None,
            spoken_followup=spoken_followup,
            executed=executed,
            logs=logs,
            store_history=True,
        )

    def _run_orchestrated(
        self,
        turn_id: str,
        user_text: str,
        kind: CommandKind,
        logs: list[str],
    ) -> TurnResult:
        agent_reply = self._assistant.run_agent_loop(user_text, routed=kind)
        logs.append("orchestrated")
        if agent_reply == AgentOrchestrator.DELEGATE_SEARCH:
            return TurnResult(
                turn_id=turn_id,
                route=RouteLane.SEARCH.value,
                user_visible="",
                early_ack=None,
                executed=False,
                logs=logs,
                delegate_search=True,
                search_intent_name=kind.name,
                search_query=None,
            )
        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.ORCHESTRATED.value,
            user_visible=agent_reply,
            early_ack=None,
            executed=True,
            logs=logs,
            store_history=True,
        )


def _frontier_enabled(assistant: IrisAssistant) -> bool:
    settings = assistant._settings
    if settings is None:
        return True
    return bool(getattr(settings, "frontier_enabled", True))


def _unified_llm_router_enabled(assistant: IrisAssistant) -> bool:
    settings = assistant._settings
    if settings is None:
        return True
    return bool(getattr(settings, "unified_llm_router_enabled", True))


def _llm_intent_router_enabled(assistant: IrisAssistant) -> bool:
    settings = assistant._settings
    if settings is None:
        return True
    return bool(getattr(settings, "llm_intent_router_enabled", True))


def _llm_approval_enabled(assistant: IrisAssistant) -> bool:
    settings = assistant._settings
    if settings is None:
        return True
    return bool(getattr(settings, "llm_approval_enabled", True))


def _is_critical_risk(risk_hint: str) -> bool:
    return (risk_hint or "").strip().lower() == "critical"


def _looks_like_cu_approval_wait(reply: str) -> bool:
    """CU 루프가 CRITICAL 도구 승인으로 멈춘 경우."""
    body = reply.strip()
    if body.startswith("Iris:"):
        body = body[5:].strip()
    low = body.lower()
    return ("승인" in body and ("응" in body or "실행" in body)) or "approval_required" in low


def _finalize_cu_reply(
    ctx: object,
    *,
    goal: str,
    slots: dict,
    reply: str,
    risk_hint: str,
) -> tuple[str, bool, list[str]]:
    """CU 응답 → user_visible, executed, logs. ask_user·승인 대기 시 pending_cu 설정."""
    from iris.core.context_manager import DialogueContext

    logs: list[str] = []
    dialogue_ctx = ctx if isinstance(ctx, DialogueContext) else None

    question = extract_user_question(reply)
    if question:
        if dialogue_ctx is not None:
            dialogue_ctx.pending_cu = PendingComputerUseGoal(
                goal=goal,
                risk_hint=risk_hint,
                prompt=question,
                slots=dict(slots),
            )
        logs.append("pending_cu_ask_user")
        return f"Iris: {question}", False, logs

    body = reply.strip()
    if not body.startswith("Iris:"):
        body = f"Iris: {body}"

    if dialogue_ctx is not None and dialogue_ctx.pending_cu is not None:
        if dialogue_ctx.pending_cu.has_pending_tool:
            logs.append("pending_cu_tool_already_set")
            return body, False, logs

    if _looks_like_cu_approval_wait(body):
        if dialogue_ctx is not None and dialogue_ctx.pending_cu is None:
            dialogue_ctx.pending_cu = PendingComputerUseGoal(
                goal=goal,
                risk_hint="critical",
                prompt=body.replace("Iris:", "").strip(),
                slots=dict(slots),
            )
        logs.append("pending_cu_set")
        return body, False, logs

    return body, True, logs


def build_user_visible(
    ack: str,
    exec_reply: str,
    *,
    had_early_ack: bool = False,
) -> str:
    """채팅·메모리용 — ack + 실행 결과 (early_ack 턴은 ack 생략)."""
    if had_early_ack:
        if not exec_reply:
            return f"Iris: {ack}" if ack else ""
        body = exec_reply.strip()
        if not body.startswith("Iris:"):
            body = f"Iris: {body}"
        return body
    if not exec_reply:
        body = ack
    elif not ack:
        body = exec_reply
    else:
        exec_body = exec_reply.strip()
        if exec_body.startswith("Iris:"):
            exec_body = exec_body[5:].strip()
        body = f"Iris: {ack} {exec_body}"
    if not body.startswith("Iris:"):
        body = f"Iris: {body}"
    return body


def build_spoken_followup(
    ack: str,
    exec_reply: str,
    *,
    had_early_ack: bool = False,
) -> str:
    """TTS follow-up — ack 문장은 제외하고 실행 결과만."""
    if had_early_ack:
        if not exec_reply:
            return ""
    elif not exec_reply:
        return ""
    body = exec_reply.strip()
    if body.startswith("Iris:"):
        body = body[5:].strip()
    ack_plain = ack.strip()
    if ack_plain and body == ack_plain:
        return ""
    if not body:
        return ""
    return f"Iris: {body}"
