"""도메인 시간 표준 (UTC ISO8601)."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """현재 UTC 시각 ISO8601 문자열."""
    return datetime.now(timezone.utc).isoformat()
