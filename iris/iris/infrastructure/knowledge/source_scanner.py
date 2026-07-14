"""지식 소스 스캔 — 증분·제외 규칙."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from iris.infrastructure.knowledge.document_extractor import TEXT_EXTENSIONS

# 민감·노이즈 경로 기본 차단
_EXCLUDE_DIR_NAMES = frozenset({
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    ".venv.broken",
    "venv",
    ".iris",
    "dist",
    "build",
    ".mypy_cache",
    "site-packages",
})
# .venv* / .pytest_tmp* — 깨진 venv 백업·테스트 tmp가 인덱싱되면 UI가 DB 락에 멈춤
_EXCLUDE_DIR_PREFIXES = (".venv", ".pytest_tmp")
_EXCLUDE_FILE_SUFFIXES = frozenset({
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".env",
})
_SENSITIVE_NAME_PARTS = frozenset({
    "id_rsa",
    "credentials",
    "secrets",
})


def _is_excluded_dir_name(name: str) -> bool:
    low = name.lower()
    if low in _EXCLUDE_DIR_NAMES:
        return True
    return any(low.startswith(prefix) for prefix in _EXCLUDE_DIR_PREFIXES)


def normalize_path(path: Path) -> str:
    """Windows 경로 정규화 — DB 키용."""
    try:
        return str(path.resolve())
    except OSError:
        return str(path.absolute())


def file_content_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def should_skip_path(path: Path) -> bool:
    """민감·제외 대상 판별."""
    name = path.name.lower()
    if name.startswith(".env"):
        return True
    if path.suffix.lower() in _EXCLUDE_FILE_SUFFIXES:
        return True
    for part in path.parts:
        low = part.lower()
        if _is_excluded_dir_name(low):
            return True
        if low in _SENSITIVE_NAME_PARTS:
            return True
    return False


@dataclass(frozen=True)
class ScannedFile:
    canonical_path: str
    title: str
    content_hash: str
    file_size: int


def iter_source_files(root: Path) -> list[ScannedFile]:
    """루트 아래 인덱싱 대상 파일 목록."""
    root = root.resolve()
    if not root.exists():
        return []
    out: list[ScannedFile] = []
    if root.is_file():
        if should_skip_path(root) or root.suffix.lower() not in TEXT_EXTENSIONS:
            return []
        try:
            st = root.stat()
            return [
                ScannedFile(
                    canonical_path=normalize_path(root),
                    title=root.stem,
                    content_hash=file_content_hash(root),
                    file_size=st.st_size,
                )
            ]
        except OSError:
            return []

    for dirpath, dirnames, filenames in os.walk(root):
        cur = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir_name(d)]
        for fname in filenames:
            fp = cur / fname
            if should_skip_path(fp):
                continue
            if fp.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                st = fp.stat()
                if st.st_size > 10 * 1024 * 1024:
                    continue
                out.append(
                    ScannedFile(
                        canonical_path=normalize_path(fp),
                        title=fp.stem,
                        content_hash=file_content_hash(fp),
                        file_size=st.st_size,
                    )
                )
            except OSError:
                continue
    return out
