"""Iris Wiki 애플리케이션 서비스."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from iris.domain.knowledge.models import KnowledgeChunk, KnowledgeSearchHit, KnowledgeSource, SourceStatus
from iris.infrastructure.knowledge.chunker import chunk_text
from iris.infrastructure.knowledge.document_extractor import extract_document
from iris.infrastructure.knowledge.embedding_client import OllamaEmbeddingClient, embedding_to_blob
from iris.infrastructure.knowledge.reference_analyzer import analyze_reference_note
from iris.infrastructure.knowledge.source_scanner import (
    iter_source_files,
    normalize_path,
    should_skip_path,
)
from iris.infrastructure.knowledge.sqlite_knowledge_index import SqliteKnowledgeIndex
from iris.infrastructure.knowledge.vault_repository import ensure_vault_layout, iris_notes_dir
from iris.storage.database import Database

if TYPE_CHECKING:
    from iris.config.settings import Settings


def resolve_iris_repo_root() -> Path | None:
    """Iris 저장소 루트(AGENTS.md) 탐색."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "AGENTS.md").is_file():
            return parent
        if (parent / "iris" / "iris" / "__init__.py").is_file() and (parent / "docs").is_dir():
            return parent
    return None


@dataclass
class SyncReport:
    indexed: int = 0
    unchanged: int = 0
    skipped: int = 0
    missing: int = 0
    failed: int = 0


class KnowledgeService:
    """Vault·소스 등록·동기화·검색."""

    def __init__(
        self,
        db: Database,
        *,
        vault_path: Path,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._vault_path = vault_path
        self._settings = settings
        self._embed: OllamaEmbeddingClient | None = None
        if settings is not None and settings.wiki_embed_enabled:
            self._embed = OllamaEmbeddingClient(settings)
        with db._lock:  # noqa: SLF001
            self._index = SqliteKnowledgeIndex(db._conn)  # noqa: SLF001

    def _locked(self) -> object:
        return self._db._lock  # noqa: SLF001

    @property
    def vault_path(self) -> Path:
        return self._vault_path

    @property
    def index(self) -> SqliteKnowledgeIndex:
        return self._index

    def init_vault(self) -> Path:
        return ensure_vault_layout(self._vault_path)

    def register_source(self, path: Path) -> int:
        canonical = normalize_path(path)
        with self._locked():
            return self._index.register_root(canonical)

    def sync(self) -> SyncReport:
        """소스 동기화 — 파일 I/O·해시는 락 밖에서 수행해 UI가 DB에 굶지 않게 한다."""
        report = SyncReport()
        seen_paths: set[str] = set()
        with self._locked():
            roots = list(self._index.list_roots())

        for root_id, root_path in roots:
            root = Path(root_path)
            # 스캔·해시: 락 없음 (OneDrive/.venv.broken 등에서 수분~수십 분 가능)
            scanned = iter_source_files(root)
            for sf in scanned:
                seen_paths.add(sf.canonical_path)
                with self._locked():
                    existing = self._index.get_source_by_path(sf.canonical_path)
                    if existing and existing.content_hash == sf.content_hash:
                        self._index.upsert_source(
                            KnowledgeSource(
                                id=existing.id,
                                root_id=root_id,
                                canonical_path=sf.canonical_path,
                                title=existing.title or sf.title,
                                status=SourceStatus.UNCHANGED.value,
                                content_hash=sf.content_hash,
                                file_size=sf.file_size,
                                updated_at=existing.updated_at,
                            )
                        )
                        report.unchanged += 1
                        continue
                    existing_id = existing.id if existing else 0

                fp = Path(sf.canonical_path)
                extracted = extract_document(fp)
                if extracted is None:
                    status = SourceStatus.SKIPPED.value
                    report.skipped += 1
                    chunks: list[KnowledgeChunk] = []
                    title = sf.title
                else:
                    status = SourceStatus.INDEXED.value
                    report.indexed += 1
                    drafts = chunk_text(extracted.body, base_heading=extracted.title)
                    chunks = [
                        KnowledgeChunk(
                            id=0,
                            source_id=0,
                            chunk_index=d.chunk_index,
                            heading=d.heading,
                            content=d.content,
                            content_hash=d.content_hash,
                            tags=extracted.tags,
                        )
                        for d in drafts
                    ]
                    title = extracted.title

                embeddings = self._embed_chunks(chunks) if chunks else []
                with self._locked():
                    source_id = self._index.upsert_source(
                        KnowledgeSource(
                            id=existing_id,
                            root_id=root_id,
                            canonical_path=sf.canonical_path,
                            title=title,
                            status=status,
                            content_hash=sf.content_hash,
                            file_size=sf.file_size,
                            updated_at="",
                        )
                    )
                    if chunks:
                        self._index.replace_chunks(source_id, chunks, embeddings=embeddings)

            root_norm = normalize_path(root)
            with self._locked():
                candidates = [
                    src
                    for src in self._index.list_sources(limit=5000)
                    if src.canonical_path.startswith(root_norm)
                    and src.canonical_path not in seen_paths
                    and src.status != SourceStatus.MISSING.value
                ]
            for src in candidates:
                with self._locked():
                    self._index.mark_missing(src.id)
                report.missing += 1

        # 이전에 잘못 인덱싱된 .venv.broken 등 제외 경로 정리 (락을 짧게)
        with self._locked():
            all_sources = self._index.list_sources(limit=10000)
        for src in all_sources:
            if src.status == SourceStatus.MISSING.value:
                continue
            if not should_skip_path(Path(src.canonical_path)):
                continue
            with self._locked():
                self._index.mark_missing(src.id)
            report.missing += 1

        with self._locked():
            self._write_iris_index_note()
            self._sync_reference_profiles_locked()
        return report

    def _embed_chunks(self, chunks: list[KnowledgeChunk]) -> list[bytes | None]:
        if self._embed is None:
            return [None] * len(chunks)
        out: list[bytes | None] = []
        for ch in chunks:
            vec = self._embed.embed_text(f"{ch.heading}\n{ch.content}")
            out.append(embedding_to_blob(vec) if vec else None)
        return out

    def _sync_reference_profiles_locked(self) -> None:
        ref_dir = self._vault_path / "30_Reference"
        if not ref_dir.is_dir():
            return
        for path in ref_dir.rglob("*.md"):
            profile = analyze_reference_note(path)
            if profile is None:
                continue
            self._index.upsert_reference_profile(
                source_path=profile.source_path,
                title=profile.title,
                style_packet=profile.style_packet,
                tags=profile.tags,
            )

    def search(self, query: str, *, limit: int = 12) -> list[KnowledgeSearchHit]:
        with self._locked():
            hits = self._index.search(query, limit=max(limit, limit * 2))
            if self._embed is not None:
                qvec = self._embed.embed_text(query)
                if qvec:
                    hits = self._index.rerank_with_embedding(hits, qvec, limit=limit)
                    return hits
            return hits[:limit]

    def search_reference_style(self, query: str, *, limit: int = 3) -> list[str]:
        with self._locked():
            return self._index.search_reference_style(query, limit=limit)

    def list_sources(self, *, limit: int = 200) -> list[KnowledgeSource]:
        with self._locked():
            return self._index.list_sources(limit=limit)

    def status(self) -> dict[str, object]:
        with self._locked():
            return {
                "vault_path": str(self._vault_path),
                "roots": self._index.list_roots(),
                "counts": self._index.status_counts(),
                "embed_enabled": self._embed is not None,
            }

    def ensure_iris_bootstrap(self, repo_root: Path | None = None) -> SyncReport:
        self.init_vault()
        root = repo_root or resolve_iris_repo_root()
        if root is not None and root.is_dir():
            self.register_source(root)
            docs = root / "docs"
            if docs.is_dir():
                self.register_source(docs)
        return self.sync()

    def get_chunk_preview(self, source_id: int, *, limit: int = 4000) -> str:
        with self._locked():
            row = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT content FROM knowledge_chunks
                WHERE source_id=?
                ORDER BY chunk_index
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()
        text = str(row[0]) if row else ""
        return text[:limit]

    def _write_iris_index_note(self) -> None:
        notes_dir = iris_notes_dir(self._vault_path)
        notes_dir.mkdir(parents=True, exist_ok=True)
        sources = self._index.list_sources(limit=80)
        lines = ["# IRIS Indexed Sources\n"]
        for src in sources:
            lines.append(f"- **{src.title}** (`{src.status}`) — `{src.canonical_path}`")
        (notes_dir / "indexed_sources.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_knowledge_service(
    db: Database,
    vault_path: Path,
    *,
    settings: Settings | None = None,
) -> KnowledgeService:
    return KnowledgeService(db, vault_path=vault_path, settings=settings)
