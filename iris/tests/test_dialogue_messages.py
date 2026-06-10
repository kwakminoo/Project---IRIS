"""DIALOGUE_CHAT 경량 메시지 조립."""

from __future__ import annotations

from pathlib import Path

from iris.ai.gemma_client import ChatMessage
from iris.ai.prompt_builder import IRIS_SYSTEM_PROMPT
from iris.assistant.dialogue_agent import DialogueAgent, build_dialogue_messages
from tests.support.fakes import FakeGemma, make_test_assistant


def test_build_dialogue_messages_excludes_full_system_and_memory(tmp_path: Path) -> None:
    gemma = FakeGemma()
    assistant = make_test_assistant(tmp_path, gemma)
    assistant.memory.add_turn("user", "이전 질문")
    assistant.memory.add_turn("assistant", "이전 답")

    agent = DialogueAgent(assistant, gemma)  # type: ignore[arg-type]
    msgs = agent.build_messages("오늘 날씨 어때?")

    assert len(msgs) >= 2
    sys = msgs[0].content
    assert IRIS_SYSTEM_PROMPT not in sys
    assert "기억·작업 세션" not in sys
    assert "Iris" in sys
    mem_extra = assistant.memory.build_extra_context()
    if mem_extra:
        assert mem_extra not in sys
    assert msgs[-1].content == "오늘 날씨 어때?"


def test_build_dialogue_messages_trims_history() -> None:
    history: list[ChatMessage] = []
    for i in range(10):
        history.append(ChatMessage("user", f"u{i}"))
        history.append(ChatMessage("assistant", f"a{i}"))

    msgs = build_dialogue_messages("현재", history=history, max_history_turns=2)
    roles_contents = [(m.role, m.content) for m in msgs if m.role != "system"]
    assert roles_contents == [
        ("user", "u8"),
        ("assistant", "a8"),
        ("user", "u9"),
        ("assistant", "a9"),
        ("user", "현재"),
    ]
