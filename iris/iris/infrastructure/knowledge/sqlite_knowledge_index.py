"""SQLite Knowledge FTS 인덱스."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from iris.domain.knowledge.models import KnowledgeChunk, KnowledgeSearchHit, KnowledgeSource, SourceStatus
from iris.infrastructure.knowledge.embedding_client import blob_to_embedding, cosine_similarity, embedding_to_blob
from iris.infrastructure.persistence.migrations import run_pending_migrations


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteKnowledgeIndex:
    """knowledge_* 테이블 CRUD·FTS 검색."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        run_pending_migrations(conn)
        self._fts_available = self._detect_fts()

    def _detect_fts(self) -> bool:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_chunks_fts'"
        ).fetchone()
        return row is not None

    def register_root(self, canonical_path: str) -> int:
        now = _now()
        self._conn.execute(
            """
            INSERT INTO knowledge_source_roots (canonical_path, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(canonical_path) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (canonical_path, now, now),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM knowledge_source_roots WHERE canonical_path=?",
            (canonical_path,),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def list_roots(self) -> list[tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT id, canonical_path FROM knowledge_source_roots ORDER BY id"
        ).fetchall()
        return [(int(r[0]), str(r[1])) for r in rows]

    def upsert_source(self, source: KnowledgeSource) -> int:
        now = _now()
        self._conn.execute(
            """
            INSERT INTO knowledge_sources
                (root_id, canonical_path, title, status, content_hash, file_size, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_path) DO UPDATE SET
                title=excluded.title,
                status=excluded.status,
                content_hash=excluded.content_hash,
                file_size=excluded.file_size,
                updated_at=excluded.updated_at
            """,
            (
                source.root_id,
                source.canonical_path,
                source.title,
                source.status,
                source.content_hash,
                source.file_size,
                now,
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM knowledge_sources WHERE canonical_path=?",
            (source.canonical_path,),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def get_source_by_path(self, canonical_path: str) -> KnowledgeSource | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge_sources WHERE canonical_path=?",
            (canonical_path,),
        ).fetchone()
        return self._row_source(row) if row else None

    def list_sources(self, *, limit: int = 500) -> list[KnowledgeSource]:
        rows = self._conn.execute(
            "SELECT * FROM knowledge_sources ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_source(r) for r in rows]

    def replace_chunks(
        self,
        source_id: int,
        chunks: list[KnowledgeChunk],
        *,
        embeddings: list[bytes | None] | None = None,
    ) -> None:
        self._conn.execute("DELETE FROM knowledge_chunks WHERE source_id=?", (source_id,))
        if self._fts_available:
            self._conn.execute(
                "DELETE FROM knowledge_chunks_fts WHERE source_id=?", (source_id,)
            )
        for i, ch in enumerate(chunks):
            emb_blob = None
            if embeddings is not None and i < len(embeddings):
                emb_blob = embeddings[i]
            self._conn.execute(
                """
                INSERT INTO knowledge_chunks
                    (source_id, chunk_index, heading, content, content_hash, tags, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    ch.chunk_index,
                    ch.heading,
                    ch.content,
                    ch.content_hash,
                    ch.tags,
                    emb_blob,
                ),
            )
            chunk_id = int(self._conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            if self._fts_available:
                src = self._conn.execute(
                    "SELECT title, canonical_path FROM knowledge_sources WHERE id=?",
                    (source_id,),
                ).fetchone()
                title = str(src[0]) if src else ""
                path = str(src[1]) if src else ""
                self._conn.execute(
                    """
                    INSERT INTO knowledge_chunks_fts
                        (chunk_id, source_id, title, path, tags, heading, content)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (chunk_id, source_id, title, path, ch.tags, ch.heading, ch.content),
                )
        self._conn.commit()

    def mark_missing(self, source_id: int) -> None:
        self._conn.execute(
            "UPDATE knowledge_sources SET status=?, updated_at=? WHERE id=?",
            (SourceStatus.MISSING.value, _now(), source_id),
        )
        self._conn.commit()

    def search(self, query: str, *, limit: int = 12) -> list[KnowledgeSearchHit]:
        q = (query or "").strip()
        if not q:
            return []
        hits: list[KnowledgeSearchHit] = []
        if self._fts_available:
            hits = self._search_fts(q, limit=limit)
        if not hits:
            hits = self._search_like(q, limit=limit)
        return hits

    def _search_fts(self, query: str, limit: int) -> list[KnowledgeSearchHit]:
        # FTS5 MATCH — 실패 시 LIKE 폴백
        try:
            rows = self._conn.execute(
                """
                SELECT
                    f.chunk_id, f.source_id, f.title, f.path, f.heading, f.content,
                    bm25(knowledge_chunks_fts) AS rank
                FROM knowledge_chunks_fts f
                WHERE knowledge_chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return self._search_like(query, limit=limit)

        hits: list[KnowledgeSearchHit] = []
        for r in rows:
            content = str(r["content"])
            hits.append(
                KnowledgeSearchHit(
                    chunk_id=int(r["chunk_id"]),
                    source_id=int(r["source_id"]),
                    title=str(r["title"]),
                    path=str(r["path"]),
                    heading=str(r["heading"] or ""),
                    snippet=content[:280],
                    score=float(-(r["rank"] or 0)),
                )
            )
        return hits

    def rerank_with_embedding(
        self,
        hits: list[KnowledgeSearchHit],
        query_vec: list[float],
        *,
        limit: int = 12,
    ) -> list[KnowledgeSearchHit]:
        """FTS 결과에 코사인 유사도 가중 — ponytail: 후보만 재정렬."""
        if not hits or not query_vec:
            return hits[:limit]
        from iris.infrastructure.knowledge.embedding_client import OllamaEmbeddingClient

        scored: list[tuple[float, KnowledgeSearchHit]] = []
        for hit in hits:
            row = self._conn.execute(
                "SELECT embedding FROM knowledge_chunks WHERE id=?",
                (hit.chunk_id,),
            ).fetchone()
            sem = 0.0
            if row and row[0]:
                doc_vec = blob_to_embedding(row[0])
                sem = cosine_similarity(query_vec, doc_vec) if doc_vec else 0.0
            iris_boost = 0.15 if "iris" in hit.path.lower() else 0.0
            score = hit.score * 0.55 + sem * 0.35 + iris_boost
            scored.append(
                (
                    score,
                    KnowledgeSearchHit(
                        chunk_id=hit.chunk_id,
                        source_id=hit.source_id,
                        title=hit.title,
                        path=hit.path,
                        heading=hit.heading,
                        snippet=hit.snippet,
                        score=score,
                    ),
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[:limit]]

    def upsert_reference_profile(
        self, *, source_path: str, title: str, style_packet: str, tags: str
    ) -> None:
        now = _now()
        self._conn.execute(
            """
            INSERT INTO knowledge_reference_profiles
                (source_path, title, style_packet, tags, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                title=excluded.title,
                style_packet=excluded.style_packet,
                tags=excluded.tags,
                updated_at=excluded.updated_at
            """,
            (source_path, title, style_packet, tags, now),
        )
        self._conn.commit()

    def search_reference_style(self, query: str, *, limit: int = 3) -> list[str]:
        like = f"%{query.strip()}%"
        rows = self._conn.execute(
            """
            SELECT style_packet FROM knowledge_reference_profiles
            WHERE title LIKE ? OR tags LIKE ? OR style_packet LIKE ?
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
        return [str(r[0]) for r in rows]

    def _search_like(self, query: str, limit: int) -> list[KnowledgeSearchHit]:
        like = f"%{query}%"
        rows = self._conn.execute(
            """
            SELECT c.id, c.source_id, s.title, s.canonical_path, c.heading, c.content
            FROM knowledge_chunks c
            JOIN knowledge_sources s ON s.id = c.source_id
            WHERE c.content LIKE ? OR s.title LIKE ? OR s.canonical_path LIKE ?
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
        return [
            KnowledgeSearchHit(
                chunk_id=int(r[0]),
                source_id=int(r[1]),
                title=str(r[2]),
                path=str(r[3]),
                heading=str(r[4] or ""),
                snippet=str(r[5])[:280],
                score=0.5,
            )
            for r in rows
        ]

    def status_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM knowledge_sources GROUP BY status"
        ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    @staticmethod
    def _row_source(row: sqlite3.Row) -> KnowledgeSource:
        return KnowledgeSource(
            id=int(row["id"]),
            root_id=int(row["root_id"]),
            canonical_path=str(row["canonical_path"]),
            title=str(row["title"]),
            status=str(row["status"]),
            content_hash=str(row["content_hash"] or ""),
            file_size=int(row["file_size"] or 0),
            updated_at=str(row["updated_at"] or ""),
        )
