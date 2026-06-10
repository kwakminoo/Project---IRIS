"""Ollama think 파라미터 전역 정책 — 호출 목적별 on/off."""

from __future__ import annotations

from enum import Enum


class LlmPurpose(str, Enum):
    """GemmaClient.chat() 호출 목적 — default 모드에서 think on/off 결정."""

    DIALOGUE_CHAT = "dialogue_chat"
    UNIFIED_ROUTER = "unified_router"
    INTENT_ROUTER = "intent_router"
    LLM_APPROVAL = "llm_approval"
    COMPUTER_USE = "computer_use"
    ORCHESTRATOR_PLAN = "orchestrator_plan"
    MODE_PRESET = "mode_preset"
    MEDIA_USER_REPLY = "media_user_reply"  # 미디어 플로우 사용자 멘트(thinking 기본 off)
    FRONTIER = "frontier"  # 앞단 1회 envelope (thinking 기본 off)
    GENERIC = "generic"


# default 모드: 다단계 실행·재계획·승인 분류는 thinking on
_DEFAULT_THINK_ON: frozenset[LlmPurpose] = frozenset(
    {
        LlmPurpose.COMPUTER_USE,
        LlmPurpose.ORCHESTRATOR_PLAN,
        LlmPurpose.LLM_APPROVAL,
    }
)

# RouteLane.COMPUTER_USE.value 와 동일 — assistant.router_policy 순환 import 방지
_LANE_COMPUTER_USE = "computer_use"


def normalize_thinking_mode(raw: str) -> str:
    """IRIS_THINKING_MODE → off | default | on."""
    key = (raw or "default").strip().lower()
    if key in {"off", "all_off", "false", "0", "no"}:
        return "off"
    if key in {"on", "all_on", "true", "1", "yes"}:
        return "on"
    return "default"


def resolve_think(
    thinking_mode: str,
    purpose: LlmPurpose,
    *,
    lane: str | None = None,
) -> bool:
    """전역 thinking 모드 + 호출 목적(+ lane)으로 Ollama think bool 결정."""
    mode = normalize_thinking_mode(thinking_mode)
    if mode == "off":
        return False
    if mode == "on":
        return True
    # default: 목적별 선택적 thinking
    if purpose in _DEFAULT_THINK_ON:
        return True
    if lane == _LANE_COMPUTER_USE:
        return True
    return False
