"""text_input_verify · text_input_controller (단위)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iris.automation import keyboard_mouse_controller as kmc
from iris.automation.text_input_controller import type_text_smart
from iris.automation.text_input_verify import (
    script_kind,
    should_verify_after_mode,
    text_matches_expected,
)


def test_script_kind_latin() -> None:
    assert script_kind("https://example.com") == "latin"


def test_script_kind_hangul() -> None:
    assert script_kind("안녕하세요") == "hangul"


def test_should_skip_verify_for_uia() -> None:
    assert should_verify_after_mode("uia_set_text", verify_enabled=True) is False
    assert should_verify_after_mode("typewrite", verify_enabled=True) is True


def test_text_matches_url_host() -> None:
    assert text_matches_expected(
        "https://www.youtube.com/watch?v=abc",
        "https://www.youtube.com/watch?v=abc111",
    )


def test_text_matches_hangul_prefix() -> None:
    assert text_matches_expected("안녕하세요", "무제 - 안녕하세요")


@patch("iris.automation.text_input_controller._attempt_type")
def test_smart_skips_verify_when_uia(mock_attempt: MagicMock) -> None:
    mock_attempt.return_value = (True, "uia_set_text", "uia_set_text")
    out = type_text_smart("안녕", verify_enabled=True, max_retries=1)
    assert out.success is True
    assert out.mode == "uia_set_text"
    assert out.verified is False
    assert out.retried is False


@patch("iris.automation.text_input_controller.read_focused_field_text")
@patch("iris.automation.text_input_controller._attempt_type")
def test_smart_no_retry_when_read_fails(
    mock_attempt: MagicMock,
    mock_read: MagicMock,
) -> None:
    mock_attempt.return_value = (True, "typewrite", "typewrite")
    mock_read.return_value = (False, "")
    out = type_text_smart("hello", verify_enabled=True, max_retries=1)
    assert out.success is True
    assert "verify_skipped" in out.message


@patch("iris.automation.text_input_controller.type_text_smart")
def test_type_text_approved_delegates(mock_smart: MagicMock) -> None:
    from iris.automation.text_input_controller import TypeTextOutcome

    mock_smart.return_value = TypeTextOutcome(True, "typewrite", "typewrite|verified", verified=True)
    ok, reason = kmc.type_text_approved("hi", approved=True, verify_enabled=False)
    assert ok is True
    assert reason.startswith("typewrite:")
