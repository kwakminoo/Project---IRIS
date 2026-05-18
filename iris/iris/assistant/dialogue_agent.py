"""DialogueAgent — 사용자에게 들리는 한국어 (짧은 ack / 일반 대화)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from iris.ai.gemma_client import ChatMessage
from iris.core.command_router import CommandKind

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient

# 실행 전 짧은 확인 — 계획·실행 내용을 invent 하지 않음
_ACK_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"유튜브|youtube", re.I), "유튜브를 열게요."),
    (re.compile(r"크롬|chrome", re.I), "Chrome을 열게요."),
    (re.compile(r"커서|cursor", re.I), "Cursor를 열게요."),
    (re.compile(r"디스코드|discord", re.I), "Discord를 열게요."),
    (re.compile(r"창", re.I), "창을 조정할게요."),
]

_DIALOGUE_SYSTEM = (
    "당신은 Iris, 사용자의 로컬 AI 비서입니다. "
    "짧고 친절한 한국어로만 답하세요. 컴퓨터 조작·앱 실행·계획은 말하지 마세요."
)


class DialogueAgent:
    """CHAT_ONLY: Gemma 1회. ACTION: 짧은 ack (템플릿 우선)."""

    def __init__(self, assistant: IrisAssistant, gemma: GemmaClient) -> None:
        self._assistant = assistant
        self._gemma = gemma

    def chat(self, user_text: str) -> str:
        """인사·잡담 — Planner·Orchestrator 없이 Gemma 1회."""
        messages = self._assistant.build_general_chat_messages(user_text)
        # 시스템 프롬프트를 대화 전용으로 덮어씀 (첫 메시지만)
        if messages and messages[0].role == "system":
            messages[0] = ChatMessage("system", _DIALOGUE_SYSTEM)
        raw = self._gemma.chat(messages)
        return self._with_iris_prefix(raw)

    def ack(self, user_text: str, kind: CommandKind) -> str:
        """실행 전 짧은 확인 문장 (템플릿, LLM 미사용)."""
        for pat, msg in _ACK_TEMPLATES:
            if pat.search(user_text):
                return msg
        if kind is CommandKind.APP_LAUNCH:
            return "요청하신 앱을 실행할게요."
        if kind is CommandKind.WINDOW_CONTROL:
            return "창을 조정할게요."
        if kind is CommandKind.MONITORING_STATUS:
            return "모니터링 상태를 확인할게요."
        return "요청을 처리할게요."

    @staticmethod
    def _with_iris_prefix(text: str) -> str:
        t = text.strip()
        if t.startswith("Iris:"):
            return t
        return f"Iris: {t}"
