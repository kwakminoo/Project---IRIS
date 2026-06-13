"""도메인 엔티티 ID 생성."""

from __future__ import annotations

import uuid


def new_id() -> str:
    """UUID4 문자열 ID."""
    return str(uuid.uuid4())
