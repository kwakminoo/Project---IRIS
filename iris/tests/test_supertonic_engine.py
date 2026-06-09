"""Supertonic 3 음성 이름 정규화."""

from __future__ import annotations

from iris.audio.supertonic_engine import resolve_supertonic_voice_name


def test_resolve_lily_display_name_to_f2() -> None:
    assert resolve_supertonic_voice_name("Lily") == "F2"
    assert resolve_supertonic_voice_name("lily") == "F2"


def test_resolve_voice_code_passthrough() -> None:
    assert resolve_supertonic_voice_name("F2") == "F2"
    assert resolve_supertonic_voice_name("f2") == "F2"


def test_resolve_default_is_lily_f2() -> None:
    assert resolve_supertonic_voice_name("") == "F2"
