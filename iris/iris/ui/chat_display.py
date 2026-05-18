"""채팅창 표시용 본문 정규화 (화자 접두사·마크다운 제거)."""

from __future__ import annotations

import re

_IRIS_PREFIX = re.compile(r"^\s*Iris\s*:\s*", re.IGNORECASE)


def strip_speaker_prefix(who: str, text: str) -> str:
    """채팅 UI가 이미 화자 이름을 붙이므로 본문의 'Iris:' 접두사는 제거한다."""
    body = (text or "").strip()
    if who.strip().lower() == "iris":
        body = _IRIS_PREFIX.sub("", body, count=1).strip()
    return body


def markdown_to_plain(text: str) -> str:
    """마크다운을 일반 텍스트로 변환 (채팅·타이핑 표시용)."""
    t = (text or "").strip()
    if not t:
        return ""

    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def normalize_chat_body(who: str, text: str) -> str:
    """채팅 패널에 넣기 전 본문 정리."""
    return markdown_to_plain(strip_speaker_prefix(who, text))
