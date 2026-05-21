"""_sanitize_visible_reply — 한글 본문이 이모지 정규식에 삭제되지 않는지."""

from __future__ import annotations

from iris.ai.gemma_client import _sanitize_visible_reply


def test_sanitize_preserves_korean_greeting() -> None:
    raw = "안녕하세요! 무엇을 도와드릴까요? 😊"
    cleaned = _sanitize_visible_reply(raw)
    assert "안녕" in cleaned
    assert "도와" in cleaned
    assert "😊" not in cleaned
    assert cleaned != "!?"


def test_sanitize_strips_thinking_tags_only() -> None:
    raw = "<thinking>internal</thinking>반갑습니다."
    cleaned = _sanitize_visible_reply(raw)
    assert cleaned == "반갑습니다."
    assert "thinking" not in cleaned.lower()
