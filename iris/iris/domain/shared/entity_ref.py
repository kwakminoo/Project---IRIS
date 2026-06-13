"""엔티티 참조 — 도구·검증 대상 식별."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityRef:
    """파일·창·프로세스 등 추상 대상 참조."""

    kind: str
    identifier: str
    label: str = ""
