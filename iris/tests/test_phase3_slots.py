"""Phase 3 — 모드 프리셋 LLM·검색 슬롯 단위 테스트."""

from __future__ import annotations

from typing import Sequence

from iris.agent.needs_agent import _query_hint_for_intent
from iris.ai.gemma_client import ChatMessage
from iris.assistant.mode_preset_resolver import resolve_mode_preset_id_llm
from iris.core.command_router import CommandKind


class _FakeGemma:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def chat(self, messages: Sequence[ChatMessage]) -> str:
        return self.reply


def test_query_hint_prefers_slot_query() -> None:
    q = _query_hint_for_intent(
        "요즘 영화 뭐 있어",
        CommandKind.MOVIE_SEARCH,
        slot_query="한국 박스오피스 추천",
    )
    assert "한국 박스오피스 추천" in q
    assert "영화" in q


def test_resolve_work_preset_from_llm() -> None:
    gemma = _FakeGemma('{"preset_id":"work_doc"}')
    pid = resolve_mode_preset_id_llm("워드로 제안서 쓸게", "work", gemma)  # type: ignore[arg-type]
    assert pid == "work_doc"


def test_resolve_rejects_unknown_preset_id() -> None:
    gemma = _FakeGemma('{"preset_id":"not_in_catalog"}')
    assert resolve_mode_preset_id_llm("x", "creative", gemma) is None  # type: ignore[arg-type]
