"""모드 프리셋 LLM·검색 슬롯 — Phase 3 현재 동작 기준."""

from __future__ import annotations

from iris.agent.needs_agent import _query_hint_for_intent
from iris.assistant.mode_preset_resolver import resolve_mode_preset_id_llm
from iris.core.command_router import CommandKind
from tests.support.fakes import FakeGemma


def test_query_hint_uses_slot_query_only() -> None:
    """Router slots.query가 있으면 user_text를 섞지 않음."""
    q = _query_hint_for_intent(
        "요즘 영화 뭐 있어",
        CommandKind.MOVIE_SEARCH,
        slot_query="한국 박스오피스 추천",
    )
    assert q == "한국 박스오피스 추천"


def test_resolve_work_preset_from_llm() -> None:
    gemma = FakeGemma(chat_reply='{"preset_id":"work_doc"}')
    pid = resolve_mode_preset_id_llm("워드로 제안서 쓸게", "work", gemma)  # type: ignore[arg-type]
    assert pid == "work_doc"


def test_resolve_rejects_unknown_preset_id() -> None:
    gemma = FakeGemma(chat_reply='{"preset_id":"not_in_catalog"}')
    assert resolve_mode_preset_id_llm("x", "creative", gemma) is None  # type: ignore[arg-type]
