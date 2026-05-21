"""대화 memory 커밋·LLM messages 중복 방지."""

from __future__ import annotations

from pathlib import Path

from iris.ai.gemma_client import ChatMessage
from iris.ai.prompt_builder import build_messages
from iris.memory.memory_manager import (
    MemoryManager,
    commit_turn_pair,
    strip_iris_prefix,
)
from iris.storage.database import Database


def test_build_messages_single_user_before_commit(tmp_path: Path) -> None:
    """진행 중 턴 — memory 비어 있으면 user 메시지 1개만."""
    msgs = build_messages("안녕", history=[])
    users = [m for m in msgs if m.role == "user"]
    assert len(users) == 1
    assert users[0].content == "안녕"


def test_build_messages_skips_duplicate_trailing_user() -> None:
    hist = [ChatMessage("user", "안녕")]
    msgs = build_messages("안녕", history=hist)
    users = [m for m in msgs if m.role == "user"]
    assert len(users) == 1


def test_build_messages_two_turn_shape(tmp_path: Path) -> None:
    """2턴째: system + u1 + a1 + u2 (u2 중복 없음)."""
    db = Database(path=tmp_path / "turn2.db")
    mem = MemoryManager(db)
    commit_turn_pair(mem, "첫 질문", "Iris: 첫 답변입니다.")
    msgs = build_messages("둘째 질문", history=mem.short_term_history())
    roles = [m.role for m in msgs]
    assert roles == ["system", "user", "assistant", "user"]
    assert msgs[-1].content == "둘째 질문"
    assert "Iris:" not in msgs[2].content


def test_commit_turn_pair_strips_iris_prefix(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "strip.db")
    mem = MemoryManager(db)
    assert commit_turn_pair(mem, "안녕", "Iris: 반갑습니다. 무엇을 도와드릴까요?")
    hist = mem.short_term_history()
    assert hist[-1].role == "assistant"
    assert hist[-1].content.startswith("반갑습니다")
    assert "Iris:" not in hist[-1].content


def test_commit_turn_pair_skips_meaningless(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "skip.db")
    mem = MemoryManager(db)
    assert not commit_turn_pair(mem, "안녕", "Iris: .,.")
    assert mem.short_term_history() == []


def test_strip_iris_prefix() -> None:
    assert strip_iris_prefix("Iris: hello") == "hello"
    assert strip_iris_prefix("iris:  test") == "test"
