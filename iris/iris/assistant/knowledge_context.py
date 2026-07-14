"""로컬 Iris Wiki → LLM 컨텍스트·필요 감지."""

from __future__ import annotations

import re
from typing import Sequence

from iris.domain.knowledge.models import KnowledgeSearchHit

# 규칙 기반 — 로컬 Wiki 선행 검색 트리거
_LOCAL_HINTS = re.compile(
    r"(아이리스|iris|프로젝트|코드|구조|아키텍처|문서|wiki|위키|obsidian|옵시디언|"
    r"memorymanager|turncoordinator|모듈|파일|저장소|구현|설정)",
    re.IGNORECASE,
)


def needs_local_knowledge(user_text: str) -> bool:
    """로컬 지식 검색이 유용한 발화인지 판별."""
    text = (user_text or "").strip()
    if len(text) < 4:
        return False
    return bool(_LOCAL_HINTS.search(text))


def build_knowledge_context(
    hits: Sequence[KnowledgeSearchHit],
    *,
    max_chunks: int = 6,
    max_chars: int = 12000,
) -> str:
    """[IRIS WIKI] 블록 생성."""
    if not hits:
        return ""
    lines = ["[IRIS WIKI]"]
    total = len(lines[0])
    used = 0
    for hit in hits[:max_chunks]:
        block = (
            f"\n---\n"
            f"제목: {hit.title}\n"
            f"경로: {hit.path}\n"
            f"섹션: {hit.heading or '(본문)'}\n"
            f"{hit.snippet.strip()}\n"
        )
        if total + len(block) > max_chars:
            break
        lines.append(block)
        total += len(block)
        used += 1
    if used == 0:
        return ""
    return "".join(lines).strip()
