"""Barge-in — SPEAKING 중 RMS 초과 시 TTS stop."""

import time
from dataclasses import replace
from unittest.mock import MagicMock

from iris.audio.barge_in import BargeInMonitor
from iris.audio.voice_session import VoiceSessionController, VoiceSessionState
from iris.config.settings import load_settings


class _FakeTts:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def test_barge_in_stops_tts_after_grace() -> None:
    tts = _FakeTts()
    monitor = BargeInMonitor(tts, grace_ms=0, threshold=0.01)
    monitor.notify_tts_started()
    time.sleep(0.01)
    triggered = monitor.check_rms(0.05)
    assert triggered is True
    assert tts.stopped is True


def test_barge_in_ignored_during_grace_period() -> None:
    tts = _FakeTts()
    monitor = BargeInMonitor(tts, grace_ms=5000, threshold=0.01)
    monitor.notify_tts_started()
    triggered = monitor.check_rms(0.05)
    assert triggered is False
    assert tts.stopped is False


def test_session_barge_listen_monitors_only_when_enabled() -> None:
    settings = replace(load_settings(), barge_in_enabled=True, voice_resume_delay_ms=0)
    session = VoiceSessionController(settings)
    session.on_tts_synthesis_started()
    session.on_tts_playback_started()
    assert session.state == VoiceSessionState.BARGE_LISTEN
    assert session.should_monitor_barge_in() is True
    assert session.should_accept_capture() is False


def test_session_emits_barge_on_trigger() -> None:
    session = VoiceSessionController(replace(load_settings()))
    slot = MagicMock()
    session.barge_in_detected.connect(slot)
    session.on_barge_in_triggered()
    slot.assert_called_once()
