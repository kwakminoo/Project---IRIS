"""레퍼런스 노트 frontmatter → Style Packet."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from iris.infrastructure.knowledge.document_extractor import extract_document

_FRONTMATTER_KV = re.compile(r"^([a-zA-Z_][\w-]*)\s*:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class ReferenceProfile:
    source_path: str
    title: str
    style_packet: str
    tags: str


def _parse_frontmatter_kv(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _FRONTMATTER_KV.finditer(raw):
        key = m.group(1).strip().lower()
        val = m.group(2).strip().strip('"').strip("'")
        out[key] = val
    return out


def analyze_reference_note(path: Path) -> ReferenceProfile | None:
    """30_Reference 등 레퍼런스 마크다운 → Style Packet."""
    if path.suffix.lower() != ".md":
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta = _parse_frontmatter_kv(raw)
    doc = extract_document(path)
    title = meta.get("title") or (doc.title if doc else path.stem)
    tone = meta.get("tone") or meta.get("voice") or ""
    audience = meta.get("audience") or ""
    tags = meta.get("tags") or (doc.tags if doc else "")
    body_sample = (doc.body if doc else raw)[:1200]
    packet_lines = [
        f"title: {title}",
        f"tags: {tags}",
    ]
    if tone:
        packet_lines.append(f"tone: {tone}")
    if audience:
        packet_lines.append(f"audience: {audience}")
    packet_lines.append("sample:")
    packet_lines.append(body_sample)
    return ReferenceProfile(
        source_path=str(path.resolve()),
        title=title,
        style_packet="\n".join(packet_lines),
        tags=tags,
    )


def style_packet_to_json(profile: ReferenceProfile) -> str:
    return json.dumps(
        {
            "title": profile.title,
            "tags": profile.tags,
            "style_packet": profile.style_packet,
            "source_path": profile.source_path,
        },
        ensure_ascii=False,
    )
