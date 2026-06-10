"""백그라운드 작업 스레드."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from iris.agent.needs_agent import research_hits_multi, research_hits_with_intent
from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.config.app_index import run_background_scan
from iris.core.activity_sink import push_activity_line
from iris.core.command_router import CommandKind
from iris.storage.database import Database

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant


class LlmWorker(QThread):
    finished_text = pyqtSignal(str)
    chunk_received = pyqtSignal(str)

    def __init__(
        self,
        client: GemmaClient,
        messages: Sequence[ChatMessage],
        *,
        stream: bool = False,
    ) -> None:
        super().__init__()
        self._client = client
        self._messages = list(messages)
        self._stream = stream

    def run(self) -> None:
        push_activity_line(
            f"Worker: LlmWorker started stream={self._stream}."
        )
        if self._stream:

            def _on_chunk(chunk: str) -> None:
                self.chunk_received.emit(chunk)

            text = self._client.chat_stream(
                self._messages,
                purpose=LlmPurpose.DIALOGUE_CHAT,
                on_chunk=_on_chunk,
            )
        else:
            text = self._client.chat(self._messages, purpose=LlmPurpose.DIALOGUE_CHAT)
        push_activity_line("Worker: LlmWorker emitting reply.")
        self.finished_text.emit(text)


class SearchWorker(QThread):
    finished_hits = pyqtSignal(str, list, str, str)  # query, hits, intent.name, meta_json

    def __init__(
        self,
        query_text: str,
        intent: CommandKind = CommandKind.WEB_SEARCH,
        *,
        slot_query: str | None = None,
        slot_queries: list[str] | None = None,
        search_meta_json: str = "",
    ) -> None:
        super().__init__()
        self._query_text = query_text
        self._intent = intent
        self._slot_query = slot_query
        self._slot_queries = slot_queries or []
        self._search_meta_json = search_meta_json

    def run(self) -> None:
        push_activity_line(
            f"Worker: SearchWorker started intent={self._intent.name}."
        )
        try:
            if self._slot_queries:
                q, hits = research_hits_multi(
                    self._query_text,
                    self._intent,
                    self._slot_queries,
                    primary_query=self._slot_query,
                )
            else:
                q, hits = research_hits_with_intent(
                    self._query_text, self._intent, slot_query=self._slot_query
                )
        except Exception as exc:
            push_activity_line(f"Worker: SearchWorker failed — {exc!s}")
            q, hits = self._query_text, []
        push_activity_line(f"Worker: SearchWorker done hits_count={len(hits)}.")
        self.finished_hits.emit(q, hits, self._intent.name, self._search_meta_json)


class AppLauncherScanWorker(QThread):
    """앱 런처 백그라운드 스캔 — UI 메인 스레드 블로킹 방지."""

    finished_scan = pyqtSignal(int, list)

    def __init__(self, db: Database, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db

    def run(self) -> None:
        push_activity_line("Worker: AppLauncherScanWorker scanning installed apps.")
        new_count, names = run_background_scan(self._db)
        push_activity_line(
            f"Worker: AppLauncherScanWorker done new_or_updated={new_count}."
        )
        self.finished_scan.emit(new_count, names)


class AgentWorker(QThread):
    """TurnCoordinator(PAV) 경유 — UI 메인 스레드 블로킹 방지."""

    # text, store_history, had_early_ack, spoken_followup(TTS용, ack 제외)
    finished_reply = pyqtSignal(str, bool, bool, str)
    delegate_search = pyqtSignal(str, str, str, str)  # user_text, intent, slot_query, meta_json
    delegate_dialogue_stream = pyqtSignal(str)  # CHAT_ONLY — UI 스트리밍 대화 (폴백)
    frontier_stream = pyqtSignal(str, bool)  # Frontier 선행 말, store_history
    early_ack = pyqtSignal(str)  # DIRECT_ACTION 실행 전 (메인 스레드 QueuedConnection)
    user_notify = pyqtSignal(str)  # 키보드·단축키 충돌 안내 (TTS)

    def __init__(self, assistant: IrisAssistant, user_text: str) -> None:
        super().__init__()
        self._assistant = assistant
        self._user_text = user_text

    def run(self) -> None:
        push_activity_line("Worker: AgentWorker pipeline started.")
        coordinator = TurnCoordinator(self._assistant, self._assistant.gemma_client)

        def _emit_early_ack(ack: str) -> None:
            self.early_ack.emit(ack)

        def _emit_frontier_reply(reply: str) -> None:
            self.frontier_stream.emit(reply, False)

        def _emit_user_notify(msg: str) -> None:
            self.user_notify.emit(msg)

        result = coordinator.run_turn(
            self._user_text,
            on_early_ack=_emit_early_ack,
            on_frontier_reply=_emit_frontier_reply,
            on_user_notify=_emit_user_notify,
        )
        if result.delegate_search:
            push_activity_line("Worker: AgentWorker delegating to search path.")
            intent_name = result.search_intent_name or CommandKind.WEB_SEARCH.name
            slot_q = (result.search_query or "").strip()
            meta = (result.search_meta_json or "").strip()
            self.delegate_search.emit(self._user_text, intent_name, slot_q, meta)
            return
        if getattr(result, "delegate_frontier_stream", False):
            push_activity_line("Worker: AgentWorker delegating to frontier stream.")
            self.frontier_stream.emit(
                getattr(result, "frontier_reply", "") or "",
                True,
            )
            return
        if getattr(result, "delegate_dialogue_stream", False):
            push_activity_line("Worker: AgentWorker delegating to streaming dialogue.")
            self.delegate_dialogue_stream.emit(self._user_text)
            return
        if result.user_visible:
            push_activity_line(
                f"Worker: AgentWorker finished route={getattr(result, 'route', 'unknown')!r} "
                f"early_ack={getattr(result, 'had_early_ack', False)}."
            )
            self.finished_reply.emit(
                result.user_visible,
                result.store_history,
                result.had_early_ack,
                result.spoken_followup or "",
            )
        else:
            push_activity_line(
                "Worker: AgentWorker ended with empty user_visible (no emit)."
            )
