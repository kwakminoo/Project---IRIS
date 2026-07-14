"""Ollama 임베딩 클라이언트 — 실패 시 None 반환."""

from __future__ import annotations

import json
import math
import struct
from typing import Sequence

import httpx

from iris.config.settings import Settings


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embedding_to_blob(vec: Sequence[float]) -> bytes:
    """float32 벡터 → BLOB."""
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_embedding(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob[: n * 4]))


class OllamaEmbeddingClient:
    """POST /api/embeddings — Ollama 전용."""

    def __init__(self, settings: Settings) -> None:
        self._base = settings.ollama_base_url.rstrip("/")
        self._model = (
            getattr(settings, "wiki_embed_model", "") or "nomic-embed-text"
        ).strip()
        self._timeout = min(30.0, float(settings.llm_timeout_seconds))

    @property
    def model_name(self) -> str:
        return self._model

    def embed_text(self, text: str) -> list[float] | None:
        body = (text or "").strip()
        if not body:
            return None
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base}/api/embeddings",
                    json={"model": self._model, "prompt": body[:8000]},
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, OSError):
            return None
        raw = data.get("embedding")
        if not isinstance(raw, list):
            return None
        try:
            return [float(x) for x in raw]
        except (TypeError, ValueError):
            return None

    def similarity(self, query_vec: Sequence[float], doc_vec: Sequence[float]) -> float:
        return cosine_similarity(query_vec, doc_vec)
