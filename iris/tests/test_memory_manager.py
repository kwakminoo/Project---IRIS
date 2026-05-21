"""MemoryManager 3계층 테스트."""

from __future__ import annotations

from pathlib import Path

from iris.memory.memory_manager import MemoryManager
from iris.storage.database import Database


def test_short_term_trim(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "m.db")
    mem = MemoryManager(db)
    for i in range(20):
        mem.add_turn("user", f"msg {i} " + "x" * 400)
    hist = mem.short_term_history()
    assert len(hist) <= 12


def test_task_session_roundtrip(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "m2.db")
    mem = MemoryManager(db, session_key="test_sess")
    mem.save_task_session(
        current_goal="테스트 목표",
        tools_run=["list_open_windows"],
        observations=["창 3개"],
    )
    ctx = mem.build_extra_context()
    assert "테스트 목표" in ctx
    assert "list_open_windows" in ctx


def test_long_term_summary(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "m3.db")
    mem = MemoryManager(db)
    mem.add_long_term_summary("chat", "사용자가 작업 모드를 요청함", "ui")
    block = mem.long_term_context_for_prompt()
    assert "작업 모드" in block


def test_build_messages_memory_injection(tmp_path: Path) -> None:
    from iris.ai.prompt_builder import build_messages

    db = Database(path=tmp_path / "m4.db")
    mem = MemoryManager(db)
    mem.save_task_session(current_goal="빌드 수정")
    msgs = build_messages("안녕", memory_context=mem.build_extra_context())
    assert msgs[0].role == "system"
    assert "빌드 수정" in msgs[0].content
    assert sum(1 for m in msgs if m.role == "user") == 1
