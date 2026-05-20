"""DialogueAgent — 사용자에게 들리는 한국어 (짧은 ack / 일반 대화)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from iris.ai.gemma_client import ChatMessage
from iris.core.command_router import CommandKind

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient

# 실행 전 짧은 확인 — 계획·실행 내용을 invent 하지 않음 (goal 원문 echo 금지)
_ACK_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"유튜브|youtube", re.I), "유튜브를 열게요."),
    (re.compile(r"크롬|chrome", re.I), "Chrome을 열게요."),
    (re.compile(r"커서|cursor", re.I), "Cursor를 열게요."),
    (re.compile(r"디스코드|discord", re.I), "Discord를 열게요."),
    (re.compile(r"메모장|notepad", re.I), "메모장을 실행할게요."),
    (re.compile(r"창", re.I), "창을 조정할게요."),
]


def match_action_ack(text: str) -> str | None:
    """goal·user_text에서 행동 설명형 ack 문장 매칭 (없으면 None)."""
    for pat, msg in _ACK_TEMPLATES:
        if pat.search(text):
            return msg
    return None

_DIALOGUE_SYSTEM = (
    "당신은 Iris, 사용자의 로컬 AI 비서입니다. "
    "짧고 친절한 한국어로만 답하세요. 마크다운 없이 일반 문장만 쓰세요. "
    "컴퓨터 조작·앱 실행·계획은 말하지 마세요."
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

    def cu_early_ack(self, goal: str, slots: dict | None = None) -> str:
        """Computer Use 실행 전 짧은 확인 — 사용자 goal 원문을 반복하지 않음."""
        g = (goal or "").strip()
        slot = slots or {}
        hint = " ".join(
            str(slot.get(k) or "")
            for k in ("app_hint", "app_key", "display_name", "query", "search_query", "title")
        )
        combined = f"{g} {hint}".strip()
        task_type = str(slot.get("task_type") or "").strip().lower()

        query = slot.get("query") or slot.get("search_query") or slot.get("title")
        if isinstance(query, str) and query.strip():
            q = query.strip()[:40]
            if re.search(r"유튜브|youtube", combined, re.I):
                return f"유튜브에서 '{q}' 검색·재생을 진행할게요."
        if re.search(r"유튜브|youtube", combined, re.I):
            return "유튜브에서 요청하신 재생을 진행할게요."
        if re.search(r"카톡|카카오", combined, re.I):
            return "카카오톡에서 요청을 진행할게요."

        if task_type == "open_app" or re.search(r"메모장|notepad", combined, re.I):
            if re.search(r"메모장|notepad", combined, re.I):
                return "메모장을 실행할게요."
        matched = match_action_ack(combined)
        if matched:
            return matched
        return "요청하신 작업을 진행할게요."

    def ack(
        self,
        user_text: str,
        kind: CommandKind,
        *,
        slots: dict | None = None,
    ) -> str:
        """실행 전 짧은 확인 문장 (display_name 슬롯 우선, 템플릿 폴백)."""
        slot = slots or {}
        disp = slot.get("display_name")
        if isinstance(disp, str) and disp.strip() and kind is CommandKind.APP_LAUNCH:
            return f"{disp.strip()}을(를) 실행할게요."
        matched = match_action_ack(user_text)
        if matched:
            return matched
        if kind is CommandKind.GET_SYSTEM_INFO:
            return "사양을 잠깐 확인할게요."
        if kind is CommandKind.OPEN_URL:
            return "링크를 열게요."
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
