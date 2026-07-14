"""Obsidian Vault 폴더 구조 생성·관리."""

from __future__ import annotations

from pathlib import Path

VAULT_SUBDIRS = (
    "00_Inbox",
    "10_Projects",
    "20_IRIS",
    "30_Reference",
    "_assets",
)


def default_vault_path() -> Path:
    return Path.home() / ".iris" / "vault"


def ensure_vault_layout(vault_path: Path) -> Path:
    """Obsidian 호환 Vault 디렉터리 생성."""
    vault_path.mkdir(parents=True, exist_ok=True)
    for name in VAULT_SUBDIRS:
        (vault_path / name).mkdir(parents=True, exist_ok=True)
    readme = vault_path / "20_IRIS" / "README.md"
    if not readme.exists():
        readme.write_text(
            "# IRIS Knowledge\n\n"
            "Iris가 인덱싱한 프로젝트·문서가 여기에 표시됩니다.\n",
            encoding="utf-8",
        )
    return vault_path.resolve()


def iris_notes_dir(vault_path: Path) -> Path:
    return vault_path / "20_IRIS"
