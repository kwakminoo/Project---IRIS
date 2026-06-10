"""스트리밍 LLM 응답 — 첫 완결 문장 경계 감지."""

from __future__ import annotations

import re

# 한국어·영문 종결 부호 (짧은 응답도 허용)
_SENTENCE_END = re.compile(
    r"(?:"
    r"[.!?…]+"
    r"|요\."
    r"|다\."
    r"|죠\."
    r"|네\."
    r"|군요\."
    r"|습니다\."
    r"|해요\."
    r"|어요\."
    r"|까\?"
    r"|나요\?"
    r"|니\?"
    r")"
)


def find_first_sentence_end(text: str) -> int | None:
    """첫 완결 문장 끝 인덱스(exclusive). 없으면 None."""
    if not text or not text.strip():
        return None
    best: int | None = None
    for m in _SENTENCE_END.finditer(text):
        if m.start() <= 0:
            continue
        end = m.end()
        if best is None or end < best:
            best = end
    return best
