"""LLM 응답에서 구조화 의도 파싱 (선택 확장)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


@dataclass
class ParsedIntent:
    raw: Optional[dict[str, Any]] = None


def try_parse_json_intent(text: str) -> ParsedIntent:
    """응답에 JSON 블록이 있으면 파싱."""
    m = _JSON_BLOCK.search(text)
    if not m:
        return ParsedIntent(raw=None)
    try:
        return ParsedIntent(raw=json.loads(m.group(0)))
    except json.JSONDecodeError:
        return ParsedIntent(raw=None)


def extract_json_object(text: str) -> dict[str, Any] | None:
    """LLM 응답에서 첫 JSON 객체 dict 추출 (Intent Router·Planner 공용)."""
    return try_parse_json_intent(text).raw
