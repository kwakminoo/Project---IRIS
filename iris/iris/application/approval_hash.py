"""arguments_hash — 승인을 도구+인수에 묶음."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def hash_arguments(arguments: dict[str, Any]) -> str:
    """정규화 JSON SHA256 해시."""
    payload = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
