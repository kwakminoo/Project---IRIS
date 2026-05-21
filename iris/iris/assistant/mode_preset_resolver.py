"""Phase 3 — 멀티턴 중 작업/게임/창작 프리셋 ID를 로컬 LLM이 catalog에서만 선택."""

from __future__ import annotations

import json
from typing import Literal

from iris.ai.gemma_client import ChatMessage, GemmaClient, FALLBACK_KO
from iris.ai.thinking_policy import LlmPurpose
from iris.ai.response_parser import extract_json_object
from iris.config.preset_modes import CREATIVE_PRESETS, GAME_PRESETS, WORK_PRESETS

ModeKey = Literal["work", "game", "creative"]

_PRESET_RESOLVER_SYSTEM = """당신은 Iris Mode Preset Resolver입니다. 사용자 답변을 보고 JSON만 출력하세요.

규칙:
- mode에 해당하는 preset_catalog의 preset_id 중 하나만 선택.
- 애매하면 가장 가까운 하나. catalog에 없는 id는 금지.
- 출력: {"preset_id": "<id>"} 만. 설명·다른 키 금지.
"""


def _catalog_for_mode(mode: ModeKey) -> list[dict[str, str]]:
    if mode == "work":
        presets = WORK_PRESETS
    elif mode == "game":
        presets = GAME_PRESETS
    else:
        presets = CREATIVE_PRESETS
    return [{"preset_id": p.id, "title": p.title} for p in presets]


def _is_llm_unavailable(text: str) -> bool:
    return text.strip() == FALLBACK_KO or text.strip().startswith("로컬 언어 모델")


def resolve_mode_preset_id_llm(
    user_text: str,
    mode: ModeKey,
    gemma: GemmaClient,
) -> str | None:
    """
    멀티턴 질문(작업 유형·게임·창작)에 대한 사용자 답 → preset_id.
    실패 시 None (호출측에서 regex match_* 폴백).
    """
    catalog = _catalog_for_mode(mode)
    allowed = {c["preset_id"] for c in catalog}
    user_block = (
        f'mode="{mode}"\n'
        f"user_reply={user_text.strip()!r}\n"
        f"preset_catalog={json.dumps(catalog, ensure_ascii=False)}"
    )
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=_PRESET_RESOLVER_SYSTEM),
        ChatMessage(role="user", content=user_block),
    ]
    raw = gemma.chat(messages, purpose=LlmPurpose.MODE_PRESET)
    if _is_llm_unavailable(raw):
        return None
    data = extract_json_object(raw)
    if not data:
        return None
    pid = data.get("preset_id")
    if not isinstance(pid, str):
        return None
    key = pid.strip()
    return key if key in allowed else None
