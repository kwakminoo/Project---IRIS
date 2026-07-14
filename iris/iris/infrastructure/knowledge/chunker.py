"""문서 청킹 — heading > paragraph 우선."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_CHUNK_CHARS = 1800


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    heading: str
    content: str
    content_hash: str


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def chunk_text(body: str, *, base_heading: str = "") -> list[ChunkDraft]:
    """마크다운·일반 텍스트를 검색 가능한 청크로 분할."""
    if not body.strip():
        return []

    sections: list[tuple[str, str]] = []
    current_heading = base_heading
    buf: list[str] = []

    for line in body.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            if buf:
                sections.append((current_heading, "\n".join(buf).strip()))
                buf = []
            current_heading = m.group(2).strip()
            continue
        buf.append(line)
    if buf:
        sections.append((current_heading, "\n".join(buf).strip()))

    if not sections:
        sections = [(base_heading, body.strip())]

    drafts: list[ChunkDraft] = []
    idx = 0
    for heading, text in sections:
        if not text:
            continue
        # ponytail: 긴 단락은 고정 길이 슬라이스 — 의미 단위 분할은 Phase 3+
        start = 0
        while start < len(text):
            piece = text[start : start + _CHUNK_CHARS].strip()
            if piece:
                drafts.append(
                    ChunkDraft(
                        chunk_index=idx,
                        heading=heading,
                        content=piece,
                        content_hash=_hash(piece),
                    )
                )
                idx += 1
            start += _CHUNK_CHARS
    return drafts
