"""thinking_policy — 전역 모드·호출 목적별 think 결정."""

from __future__ import annotations

import pytest

from iris.ai.thinking_policy import LlmPurpose, normalize_thinking_mode, resolve_think


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("off", "off"),
        ("OFF", "off"),
        ("all_off", "off"),
        ("on", "on"),
        ("all_on", "on"),
        ("default", "default"),
        ("", "default"),
    ],
)
def test_normalize_thinking_mode(raw: str, expected: str) -> None:
    assert normalize_thinking_mode(raw) == expected


@pytest.mark.parametrize("purpose", list(LlmPurpose))
def test_mode_off_always_false(purpose: LlmPurpose) -> None:
    assert resolve_think("off", purpose) is False


@pytest.mark.parametrize("purpose", list(LlmPurpose))
def test_mode_on_always_true(purpose: LlmPurpose) -> None:
    assert resolve_think("on", purpose) is True


def test_mode_default_selective() -> None:
    assert resolve_think("default", LlmPurpose.DIALOGUE_CHAT) is False
    assert resolve_think("default", LlmPurpose.UNIFIED_ROUTER) is False
    assert resolve_think("default", LlmPurpose.INTENT_ROUTER) is False
    assert resolve_think("default", LlmPurpose.MODE_PRESET) is False
    assert resolve_think("default", LlmPurpose.GENERIC) is False
    assert resolve_think("default", LlmPurpose.COMPUTER_USE) is True
    assert resolve_think("default", LlmPurpose.ORCHESTRATOR_PLAN) is True
    assert resolve_think("default", LlmPurpose.LLM_APPROVAL) is True


def test_mode_default_lane_computer_use() -> None:
    assert (
        resolve_think("default", LlmPurpose.GENERIC, lane="computer_use") is True
    )
