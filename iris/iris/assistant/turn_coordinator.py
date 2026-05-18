"""TurnCoordinator — 한 턴 Router·Dialogue·Planner·Executor 결과 병합."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from iris.assistant.dialogue_agent import DialogueAgent
from iris.assistant.orchestrator import AgentOrchestrator
from iris.assistant.router_policy import RouteLane, RoutedTurn, resolve_route_lane
from iris.assistant.safety_guard import quick_block_user_text
from iris.core.command_router import CommandKind
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

        kind = routed if routed is not None else route_user_intent(user_text)
        routed_turn = resolve_route_lane(user_text, kind, self._assistant.ctx)
        lane = routed_turn.lane
        logs.append(f"lane={lane.value} kind={kind.name}")

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

        if lane is RouteLane.DIRECT_ACTION:
            return self._run_direct_action(
                turn_id, user_text, routed_turn, logs, on_early_ack=on_early_ack
            )

        # ORCHESTRATED — 기존 AgentOrchestrator (Planner 포함)
        return self._run_orchestrated(turn_id, user_text, kind, logs)

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
        ack = self._dialogue.ack(user_text, kind)
        logs.append(f"ack={ack[:40]}")

        if on_early_ack is not None:
            on_early_ack(ack)
        logs.append("early_ack_callback")

        exec_reply = ""
        executed = False

        if routed.open_url:
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

        user_visible = build_user_visible(ack, exec_reply)
        spoken_followup = build_spoken_followup(ack, exec_reply)
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

def build_user_visible(ack: str, exec_reply: str) -> str:
    """채팅·메모리용 — ack + 실행 결과 전체."""
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


def build_spoken_followup(ack: str, exec_reply: str) -> str:
    """TTS follow-up — ack 문장은 제외하고 실행 결과만."""
    if not exec_reply:
        return ""
    body = exec_reply.strip()
    if body.startswith("Iris:"):
        body = body[5:].strip()
    # exec만 있는 경우 ack 템플릿이 본문에 섞이지 않도록 ack 단독 중복 방지
    ack_plain = ack.strip()
    if ack_plain and body == ack_plain:
        return ""
    if not body:
        return ""
    return f"Iris: {body}"
