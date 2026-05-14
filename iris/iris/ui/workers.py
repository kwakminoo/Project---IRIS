"""백그라운드 작업 스레드."""

from __future__ import annotations

from typing import Sequence

from PyQt6.QtCore import QThread, pyqtSignal

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.agent.needs_agent import research_hits


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
    finished_hits = pyqtSignal(str, list)

    def __init__(self, query_text: str) -> None:
        super().__init__()
        self._query_text = query_text

    def run(self) -> None:
        q, hits = research_hits(self._query_text)
        self.finished_hits.emit(q, hits)
