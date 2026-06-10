"""스트리밍 첫 문장 경계."""

from __future__ import annotations

from iris.ai.stream_sentence import find_first_sentence_end


def test_find_first_sentence_end_korean() -> None:
    assert find_first_sentence_end("안녕하세요.") == 6
    assert find_first_sentence_end("반가워요! 또 만났네요.") == 5


def test_find_first_sentence_end_incomplete() -> None:
    assert find_first_sentence_end("아직 문장이") is None
