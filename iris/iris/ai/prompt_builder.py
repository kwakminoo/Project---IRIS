"""시스템 프롬프트 및 대화 조립."""

from __future__ import annotations

from typing import Sequence

from iris.ai.gemma_client import ChatMessage

IRIS_SYSTEM_PROMPT = """당신은 Iris, 사용자의 개인 AI 비서입니다.
역할은 사용자의 컴퓨터 작업을 돕고, 필요한 앱과 창을 정리하며, 작업 흐름이 끊기지 않도록 관리하는 것입니다.
한국어로 짧고 명확하게 답변하세요.
사용자가 바로 행동할 수 있게 말하세요.
위험한 컴퓨터 조작은 반드시 사용자 승인을 요구하세요.
모르는 정보는 추측하지 말고 확인이 필요하다고 말하세요.
사용자가 작업 모드나 게임 모드를 요청하면 바로 실행하지 말고, 어떤 작업이나 게임을 실행할지 먼저 물어보세요.
최근 작업 기록이 있으면 이어갈지 물어보세요."""


def build_messages(
    user_text: str,
    extra_context: str | None = None,
    history: Sequence[ChatMessage] | None = None,
    *,
    memory_context: str | None = None,
) -> list[ChatMessage]:
    """시스템 + (선택)메모리·컨텍스트 + 히스토리 + 사용자 메시지."""
    sys = IRIS_SYSTEM_PROMPT
    if memory_context:
        sys = sys + "\n\n[기억·작업 세션]\n" + memory_context.strip()
    if extra_context:
        sys = sys + "\n\n[컨텍스트]\n" + extra_context.strip()
    out: list[ChatMessage] = [ChatMessage("system", sys)]
    if history:
        out.extend(history)
    out.append(ChatMessage("user", user_text))
    return out
