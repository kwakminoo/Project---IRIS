"""Iris Wiki 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceStatus(str, Enum):
    """인덱싱된 소스 파일 상태."""

    INDEXED = "indexed"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"
    MISSING = "missing"
    EXTRACTION_FAILED = "extraction_failed"


@dataclass(frozen=True)
class KnowledgeSource:
    """등록된 지식 소스(파일·디렉터리) 메타."""

    id: int
    root_id: int
    canonical_path: str
    title: str
    status: str
    content_hash: str
    file_size: int
    updated_at: str


@dataclass(frozen=True)
class KnowledgeChunk:
    """검색·LLM 컨텍스트용 청크."""

    id: int
    source_id: int
    chunk_index: int
    heading: str
    content: str
    content_hash: str
    tags: str


@dataclass(frozen=True)
class KnowledgeSearchHit:
    """검색 결과."""

    chunk_id: int
    source_id: int
    title: str
    path: str
    heading: str
    snippet: str
    score: float
