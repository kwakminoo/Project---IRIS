"""Iris Wiki 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from iris.application.knowledge_service import KnowledgeService
from iris.assistant.knowledge_context import build_knowledge_context, needs_local_knowledge
from iris.domain.knowledge.models import KnowledgeSearchHit
from iris.infrastructure.knowledge.chunker import chunk_text
from iris.infrastructure.knowledge.document_extractor import extract_document
from iris.infrastructure.knowledge.source_scanner import normalize_path, should_skip_path
from iris.infrastructure.knowledge.vault_repository import ensure_vault_layout
from iris.storage.database import Database


def test_normalize_path_windows(tmp_path: Path) -> None:
    p = tmp_path / "docs" / "readme.md"
    p.parent.mkdir(parents=True)
    p.write_text("# hi", encoding="utf-8")
    norm = normalize_path(p)
    assert norm.endswith("readme.md")


def test_should_skip_env() -> None:
    assert should_skip_path(Path(".env")) is True
    assert should_skip_path(Path("node_modules/pkg/a.py")) is True
    assert should_skip_path(Path("iris/.venv.broken/Lib/site-packages/x.py")) is True
    assert should_skip_path(Path("iris/.pytest_tmp3/out.txt")) is True


def test_chunk_markdown_heading() -> None:
    body = "# Title\n\npara one\n\n## Sub\n\npara two"
    chunks = chunk_text(body, base_heading="root")
    assert len(chunks) >= 2
    assert any("Sub" in c.heading or "para" in c.content for c in chunks)


def test_extract_markdown_frontmatter(tmp_path: Path) -> None:
    md = tmp_path / "note.md"
    md.write_text("---\ntitle: Iris Wiki\ntags: [iris]\n---\n# Body\nhello", encoding="utf-8")
    doc = extract_document(md)
    assert doc is not None
    assert doc.title == "Iris Wiki"
    assert "hello" in doc.body


def test_knowledge_service_sync_and_search(tmp_path: Path) -> None:
    db = Database(tmp_path / "k.db")
    vault = tmp_path / "vault"
    svc = KnowledgeService(db, vault_path=vault)
    svc.init_vault()

    src = tmp_path / "project"
    src.mkdir()
    (src / "AGENTS.md").write_text("# Iris\n\nMemoryManager는 메모리를 관리합니다.", encoding="utf-8")
    (src / "module.py").write_text("class Foo:\n    pass\n", encoding="utf-8")

    svc.register_source(src)
    report = svc.sync()
    assert report.indexed >= 2

    hits = svc.search("Iris")
    assert hits
    assert "MemoryManager" in hits[0].snippet or "메모리" in hits[0].snippet

    ctx = build_knowledge_context(hits)
    assert "[IRIS WIKI]" in ctx


def test_needs_local_knowledge_rules() -> None:
    assert needs_local_knowledge("아이리스 MemoryManager 구조 알려줘") is True
    assert needs_local_knowledge("안녕") is False


def test_migration_007_applied(tmp_path: Path) -> None:
    db = Database(tmp_path / "m.db")
    with db._lock:  # noqa: SLF001
        row = db._conn.execute(  # noqa: SLF001
            "SELECT name FROM sqlite_master WHERE name='knowledge_sources'"
        ).fetchone()
    assert row is not None


def test_vault_layout(tmp_path: Path) -> None:
    vault = ensure_vault_layout(tmp_path / "vault")
    assert (vault / "20_IRIS" / "README.md").is_file()
