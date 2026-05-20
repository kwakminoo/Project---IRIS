"""TurnCoordinator — 한 턴 Router·Dialogue·Planner·Executor 결과 병합."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from iris.assistant.dialogue_agent import DialogueAgent
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
from iris.core.command_router import CommandKind
from iris.core.context_manager import PendingComputerUseGoal
from iris.core.intent_router import route_user_intent

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient


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
    search_intent_name: str | None = None
    store_history: bool = False

    @property
    def had_early_ack(self) -> bool:
        return self.early_ack is not None


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
    ) -> TurnResult:
        turn_id = uuid.uuid4().hex[:12]
        logs: list[str] = []

        block = quick_block_user_text(user_text)
        if block:
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

        # 1차: Unified LLM Router (실패 시 legacy_classify + resolve_route_lane 폴백)
        if is_multi_turn_active(ctx):
            kind = routed if routed is not None else route_user_intent(user_text)
            routed_turn = resolve_route_lane(user_text, kind, ctx)
        elif _unified_llm_router_enabled(self._assistant):
            routed_turn = route_user_turn(
                user_text, ctx, self._gemma, assistant=self._assistant
            )
        elif _llm_intent_router_enabled(self._assistant):
            kind = routed if routed is not None else route_user_intent(user_text)
            routed_turn = route_with_llm(
                user_text, ctx, self._gemma, fallback_kind=kind
            )
        else:
            kind = routed if routed is not None else route_user_intent(user_text)
            routed_turn = resolve_route_lane(user_text, kind, ctx)
        lane = routed_turn.lane
        kind = routed_turn.kind
        logs.append(f"lane={lane.value} kind={kind.name}")

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

        if lane is RouteLane.SEARCH:
            return TurnResult(
                turn_id=turn_id,
                route=lane.value,
                user_visible="",
                early_ack=None,
                executed=False,
                logs=logs,
                delegate_search=True,
                search_intent_name=kind.name,
            )

        if lane is RouteLane.CHAT_ONLY:
            reply = self._dialogue.chat(user_text)
            logs.append("dialogue_chat")
            return TurnResult(
                turn_id=turn_id,
                route=lane.value,
                user_visible=reply,
                early_ack=None,
                executed=False,
                logs=logs,
                store_history=True,
            )

        if lane is RouteLane.MULTI_TURN:
            reply = self._assistant.handle_user_text(user_text, routed=kind)
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
            return self._run_computer_use(
                turn_id,
                user_text,
                routed_turn,
                logs,
                on_early_ack=on_early_ack,
            )

        if lane is RouteLane.FAST_TOOL:
            return self._run_fast_tool(
                turn_id, user_text, routed_turn, logs, on_early_ack=on_early_ack
            )

        if lane is RouteLane.DIRECT_ACTION:
            return self._run_direct_action(
                turn_id, user_text, routed_turn, logs, on_early_ack=on_early_ack
            )

        # ORCHESTRATED — 기존 AgentOrchestrator (Planner 포함)
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
            self._assistant.ctx.clear_pending_cu()
            logs.append("pending_cu_cleared_unrelated")
            return None

        if cls.decision is not FollowupDecision.APPROVE:
            return None

        # CRITICAL 대기 스텝: 승인 후 1스텝만 실행 (CU 루프 재시작 금지)
        if pending.has_pending_tool:
            tool_name = pending.pending_tool_name
            params = dict(pending.pending_tool_params)
            preview = pending.pending_tool_preview
            self._assistant.ctx.clear_pending_cu()
            body = self._assistant.run_pending_cu_tool(
                tool_name,
                params,
                summary=preview or pending.goal,
            )
            logs.append("pending_cu_tool_executed")
            user_visible = body if body.startswith("Iris:") else f"Iris: {body}"
            return TurnResult(
                turn_id=turn_id,
                route=RouteLane.COMPUTER_USE.value,
                user_visible=user_visible,
                early_ack=None,
                executed=True,
                logs=logs + ["pending_cu_approved"],
                store_history=True,
            )

        goal = pending.goal
        slots = dict(pending.slots)
        self._assistant.ctx.clear_pending_cu()
        reply = self._assistant.run_computer_use_loop(
            user_text, goal=goal, slots=slots or None
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
    ) -> TurnResult:
        """CU 레인 — early_ack 후 goal/slots로 PAV 루프."""
        ctx = self._assistant.ctx
        cu_goal = (routed_turn.goal or user_text).strip()
        slots = dict(routed_turn.slots)
        if routed_turn.task_type:
            slots.setdefault("task_type", routed_turn.task_type)
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
        user_visible = build_user_visible(ack, exec_reply, had_early_ack=had_early)
        spoken_followup = build_spoken_followup(ack, exec_reply, had_early_ack=had_early)
        logs.append("computer_use")
        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.COMPUTER_USE.value,
            user_visible=user_visible,
            early_ack=ack,
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
    ) -> TurnResult:
        """ack → (콜백) → 실행(handle_user_text / open_url) → 병합 메시지."""
        kind = routed.kind
        slots = dict(routed.slots)
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

        user_visible = build_user_visible(ack, exec_reply, had_early_ack=had_early)
        spoken_followup = build_spoken_followup(ack, exec_reply, had_early_ack=had_early)
        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.DIRECT_ACTION.value,
            user_visible=user_visible,
            early_ack=ack,
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
    ) -> TurnResult:
        """Tier 1 전용 도구 1스텝 (Computer Use 루프 생략)."""
        kind = routed.kind
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

        user_visible = build_user_visible(ack, exec_reply, had_early_ack=had_early)
        spoken_followup = build_spoken_followup(ack, exec_reply, had_early_ack=had_early)

        return TurnResult(
            turn_id=turn_id,
            route=RouteLane.FAST_TOOL.value,
            user_visible=user_visible,
            early_ack=ack,
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
