"""Jarvis형 turn-taking — 음성 세션 상태 단일 진실 소스."""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from iris.config.settings import Settings


class VoiceSessionState(Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    BARGE_LISTEN = "barge_listen"


class VoiceSessionController(QObject):
    """
    Half-duplex turn-taking 상태머신.
    ContinuousListenController는 should_accept_capture()를 매 콜백에서 조회한다.
    """

    state_changed = pyqtSignal(object)
    utterance_rejected = pyqtSignal(str)
    barge_in_detected = pyqtSignal()

    def __init__(
        self,
        settings: "Settings",
        *,
        on_followup_pause: Callable[[], None] | None = None,
        on_followup_resume: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._state = VoiceSessionState.IDLE
        self._resume_until = 0.0
        self._lock = threading.Lock()
        self._on_followup_pause = on_followup_pause
        self._on_followup_resume = on_followup_resume
        self._barge_in_enabled = settings.barge_in_enabled

    @property
    def state(self) -> VoiceSessionState:
        return self._state

    def _set_state(self, new_state: VoiceSessionState) -> None:
        with self._lock:
            if self._state == new_state:
                return
            old = self._state
            self._state = new_state
        self.state_changed.emit(new_state)
        if new_state in (
            VoiceSessionState.SPEAKING,
            VoiceSessionState.BARGE_LISTEN,
            VoiceSessionState.PROCESSING,
            VoiceSessionState.TRANSCRIBING,
        ):
            if old not in (
                VoiceSessionState.SPEAKING,
                VoiceSessionState.BARGE_LISTEN,
                VoiceSessionState.PROCESSING,
                VoiceSessionState.TRANSCRIBING,
            ):
                if self._on_followup_pause:
                    self._on_followup_pause()
        elif new_state == VoiceSessionState.IDLE:
            if self._on_followup_resume:
                self._on_followup_resume()

    def _in_resume_delay(self) -> bool:
        return time.time() < self._resume_until

    def should_accept_capture(self) -> bool:
        """Half-duplex: TTS/처리/변환 중 및 resume tail 동안 수집 금지."""
        if self._in_resume_delay():
            return False
        return self._state in (VoiceSessionState.IDLE, VoiceSessionState.CAPTURING)

    def should_monitor_barge_in(self) -> bool:
        return (
            self._barge_in_enabled
            and self._state == VoiceSessionState.BARGE_LISTEN
            and not self._in_resume_delay()
        )

    def should_run_stt(self, audio: np.ndarray) -> bool:
        """no-speech gate 전 — 오디오 에너지가 너무 낮으면 STT 생략."""
        if audio.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float32)))))
        floor = self._settings.always_listen_silence_rms * 0.8
        return rms >= floor

    def on_speech_segment_started(self) -> None:
        if self.should_accept_capture():
            self._set_state(VoiceSessionState.CAPTURING)

    def on_silence_boundary(self) -> None:
        self._set_state(VoiceSessionState.TRANSCRIBING)

    def on_stt_rejected(self, reason: str) -> None:
        self.utterance_rejected.emit(reason)
        self._set_state(VoiceSessionState.IDLE)

    def on_stt_accepted(self) -> None:
        self._set_state(VoiceSessionState.PROCESSING)

    def on_tts_synthesis_started(self) -> None:
        self._set_state(VoiceSessionState.SPEAKING)

    def on_tts_playback_started(self) -> None:
        if self._barge_in_enabled:
            self._set_state(VoiceSessionState.BARGE_LISTEN)
        else:
            self._set_state(VoiceSessionState.SPEAKING)

    def on_tts_playback_finished(self) -> None:
        delay_ms = self._settings.voice_resume_delay_ms
        self._resume_until = time.time() + delay_ms / 1000.0
        self._set_state(VoiceSessionState.IDLE)

    def on_agent_processing_started(self) -> None:
        self._set_state(VoiceSessionState.PROCESSING)

    def on_agent_processing_finished(self) -> None:
        if self._state == VoiceSessionState.PROCESSING:
            self._set_state(VoiceSessionState.IDLE)

    def on_barge_in_triggered(self) -> None:
        self.barge_in_detected.emit()
        self._set_state(VoiceSessionState.CAPTURING)

    def enter_listening(self) -> None:
        """barge-in 후 즉시 수집 허용."""
        self._resume_until = 0.0
        self._set_state(VoiceSessionState.CAPTURING)

    def set_barge_in_enabled(self, enabled: bool) -> None:
        self._barge_in_enabled = enabled

    def reset_to_idle(self) -> None:
        self._resume_until = 0.0
        self._set_state(VoiceSessionState.IDLE)
