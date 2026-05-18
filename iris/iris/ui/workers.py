"""백그라운드 작업 스레드."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from PyQt6.QtCore import QThread, pyqtSignal

from iris.agent.needs_agent import format_hits_for_gemma_context, research_hits_with_intent
from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.assistant.orchestrator import AgentOrchestrator
from iris.assistant.tool_layer import is_search_intent
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.core.command_router import CommandKind
from iris.core.intent_router import route_user_intent

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant


class LlmWorker(QThread):
    finished_text = pyqtSignal(str)

    def __init__(self, client: GemmaClient, messages: Sequence[ChatMessage]) -> None:
        super().__init__()
        self._client = client
        self._messages = list(messages)

    def run(self) -> None:
        text = self._client.chat(self._messages)
        self.finished_text.emit(text)


class SearchWorker(QThread):
    finished_hits = pyqtSignal(str, list, str)

    def __init__(self, query_text: str, intent: CommandKind = CommandKind.WEB_SEARCH) -> None:
        super().__init__()
        self._query_text = query_text
        self._intent = intent

    def run(self) -> None:
        q, hits = research_hits_with_intent(self._query_text, self._intent)
        self.finished_hits.emit(q, hits, self._intent.name)


class AgentWorker(QThread):
    """handle_user_text + run_agent_loop — UI 메인 스레드 블로킹 방지."""

    # text, store_history, had_early_ack, spoken_followup(TTS용, ack 제외)
    finished_reply = pyqtSignal(str, bool, bool, str)
    delegate_search = pyqtSignal(str, str)  # user_text, intent.name
    early_ack = pyqtSignal(str)  # DIRECT_ACTION 실행 전 (메인 스레드 QueuedConnection)

    def __init__(
        self,
        assistant: IrisAssistant,
        user_text: str,
        *,
        multi_agent: bool = False,
    ) -> None:
        super().__init__()
        self._assistant = assistant
        self._user_text = user_text
        self._multi_agent = multi_agent

    def run(self) -> None:
        text = self._user_text
        if self._multi_agent:
            self._run_multi_agent_turn(text)
            return
        self._run_legacy_turn(text)

    def _run_multi_agent_turn(self, text: str) -> None:
        coordinator = TurnCoordinator(self._assistant, self._assistant.gemma_client)

        def _emit_early_ack(ack: str) -> None:
            self.early_ack.emit(ack)

        result = coordinator.run_turn(text, on_early_ack=_emit_early_ack)
        if result.delegate_search:
            intent_name = result.search_intent_name or CommandKind.WEB_SEARCH.name
            self.delegate_search.emit(text, intent_name)
            return
        if result.user_visible:
            self.finished_reply.emit(
                result.user_visible,
                result.store_history,
                result.had_early_ack,
                result.spoken_followup or "",
            )

    def _run_legacy_turn(self, text: str) -> None:
        intent = route_user_intent(text)
        if is_search_intent(intent):
            self.delegate_search.emit(text, intent.name)
            return
        reply = self._assistant.handle_user_text(text, routed=intent)
        if reply:
            self.finished_reply.emit(reply, False, False, "")
            return
        agent_reply = self._assistant.run_agent_loop(text, routed=intent)
        if agent_reply == AgentOrchestrator.DELEGATE_SEARCH:
            self.delegate_search.emit(text, intent.name)
            return
        self.finished_reply.emit(agent_reply, True, False, "")
