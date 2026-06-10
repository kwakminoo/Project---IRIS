"""VoiceSessionController half-duplex — SPEAKING 중 capture 금지."""

import numpy as np
from dataclasses import replace

from iris.audio.voice_session import VoiceSessionController, VoiceSessionState
from iris.config.settings import load_settings


def _session() -> VoiceSessionController:
    return VoiceSessionController(replace(load_settings(), voice_resume_delay_ms=0))


def test_idle_allows_capture() -> None:
    session = _session()
    assert session.should_accept_capture() is True


def test_speaking_blocks_capture() -> None:
    session = _session()
    session.on_tts_synthesis_started()
    session.on_tts_playback_started()
    assert session.state in (VoiceSessionState.SPEAKING, VoiceSessionState.BARGE_LISTEN)
    assert session.should_accept_capture() is False


def test_transcribing_blocks_capture() -> None:
    session = _session()
    session.on_silence_boundary()
    assert session.state == VoiceSessionState.TRANSCRIBING
    assert session.should_accept_capture() is False


def test_should_run_stt_rejects_silent_audio() -> None:
    session = _session()
    silent = np.zeros(1600, dtype=np.float32)
    assert session.should_run_stt(silent) is False
