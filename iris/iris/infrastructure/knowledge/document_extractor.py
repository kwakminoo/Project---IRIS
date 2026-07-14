"""문서 본문 추출 — 확장자별 최소 구현."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TEXT_EXTENSIONS = frozenset({
    ".md", ".txt", ".py", ".json", ".mdc", ".yaml", ".yml", ".toml", ".rst", ".sql",
})
MAX_BYTES = 10 * 1024 * 1024

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class ExtractedDocument:
    title: str
    body: str
    tags: str


def extract_document(path: Path) -> ExtractedDocument | None:
    """텍스트 파일 추출. 실패 시 None."""
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None
    try:
        size = path.stat().st_size
        if size > MAX_BYTES:
            return None
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    title = path.stem
    tags = ""
    body = raw
    if path.suffix.lower() == ".md":
        fm_match = _FRONTMATTER_RE.match(raw)
        if fm_match:
            fm = fm_match.group(0)
            body = raw[fm_match.end() :]
            tag_match = re.search(r"^tags:\s*\[(.*?)\]", fm, re.MULTILINE)
            if tag_match:
                tags = tag_match.group(1).replace('"', "").replace("'", "")
            title_match = re.search(r"^title:\s*(.+)$", fm, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip().strip('"').strip("'")
        heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if heading and title == path.stem:
            title = heading.group(1).strip()
    return ExtractedDocument(title=title, body=body.strip(), tags=tags)
