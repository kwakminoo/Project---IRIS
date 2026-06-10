"""상시 음성 대기: 에너지 VAD로 발화 구간을 잡고 STT 후 시그널로 전달."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from iris.audio.barge_in import BargeInMonitor
from iris.audio.echo_cancellation import EchoCancellationAdapter
from iris.audio.mic_level import rms_to_display_level
from iris.audio.input_device import resolve_input_device
from iris.audio.vad_calibrator import VadCalibrator
from iris.core.activity_sink import push_activity_line

if TYPE_CHECKING:
    from iris.audio.stt_engine import SttEngine
    from iris.audio.voice_session import VoiceSessionController
    from iris.config.settings import Settings


class ContinuousListenController(QObject):
    """
    백그라운드 마이크 스트림 + RMS VAD.
    VoiceSessionController가 half-duplex·barge-in을 제어한다.
    """

    utterance_ready = pyqtSignal(str)
    utterance_failed = pyqtSignal()
    utterance_rejected = pyqtSignal(str)
    listen_failed = pyqtSignal(str)
    mic_level = pyqtSignal(float)
    speech_started = pyqtSignal()
    stt_started = pyqtSignal()

    def __init__(
        self,
        settings: "Settings",
        stt: "SttEngine",
        session: "VoiceSessionController",
        *,
        barge: BargeInMonitor | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._stt = stt
        self._session = session
        self._barge = barge
        self._vad = VadCalibrator(settings)
        self._aec = EchoCancellationAdapter()
        self._thread: Optional[threading.Thread] = None
        self._stream_active = threading.Event()
        self._speech_rms = settings.always_listen_speech_rms
        self._silence_rms = settings.always_listen_silence_rms

    def start(self) -> None:
        """상시 듣기 스레드 시작."""
        if self._thread and self._thread.is_alive():
            return
        self._stream_active.set()
        self._thread = threading.Thread(target=self._run_loop, name="iris-continuous-listen", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        """레거시 호환 — VoiceSessionController가 실제 half-duplex를 담당."""

    def resume(self) -> None:
        """레거시 호환."""

    def stop(self) -> None:
        self._stream_active.clear()

    def _transcribe_and_emit(self, audio: np.ndarray, sample_rate: int) -> None:
        if not self._session.should_run_stt(audio):
            push_activity_line("STT: rejected pre-gate (low energy).")
            self._session.on_stt_rejected("low_energy")
            self.utterance_rejected.emit("low_energy")
            return

        result = self._stt.transcribe(audio, sample_rate)
        if result.no_speech or not result.text:
            reason = result.reject_reason or "no_speech"
            push_activity_line(f"STT: rejected no_speech {reason}.")
            self._session.on_stt_rejected(reason)
            self.utterance_rejected.emit(reason)
            return

        self._session.on_stt_accepted()
        self.utterance_ready.emit(result.text.strip())

    def _run_loop(self) -> None:
        try:
            import sounddevice as sd
        except Exception:
            self.listen_failed.emit("sounddevice 미설치로 상시 음성 인식을 사용할 수 없습니다.")
            return

        if not self._settings.use_whisper:
            self.listen_failed.emit("USE_WHISPER=false — 상시 음성 인식이 꺼져 있습니다.")
            return

        sample_rate = self._settings.always_listen_sample_rate
        block = int(sample_rate * 0.1)
        silence_ms = self._settings.always_listen_silence_ms
        min_speech_ms = self._settings.always_listen_min_speech_ms
        max_seconds = self._settings.always_listen_max_seconds
        device_choice, device_reason = resolve_input_device(
            sd,
            self._settings.always_listen_input_device,
        )
        if device_choice is None:
            self.listen_failed.emit(device_reason)
            return
        device = device_choice.device

        in_speech = False
        speech_chunks: list[np.ndarray] = []
        speech_started_at = 0.0
        silence_started: Optional[float] = None

        def reset_utterance() -> None:
            nonlocal in_speech, speech_chunks, speech_started_at, silence_started
            in_speech = False
            speech_chunks = []
            speech_started_at = 0.0
            silence_started = None

        def finalize_utterance() -> None:
            nonlocal speech_chunks
            if not speech_chunks:
                reset_utterance()
                return
            audio = np.concatenate(speech_chunks, axis=0)
            speech_chunks = []
            reset_utterance()
            if audio.size < int(sample_rate * min_speech_ms / 1000):
                return
            self._session.on_silence_boundary()
            self.stt_started.emit()
            threading.Thread(
                target=self._transcribe_and_emit,
                args=(audio, sample_rate),
                name="iris-stt-utterance",
                daemon=True,
            ).start()

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            nonlocal in_speech, speech_started_at, silence_started
            if not self._stream_active.is_set():
                return
            mono = np.asarray(indata[:, 0], dtype=np.float32)
            mono = self._aec.process_capture(mono)
            rms = float(np.sqrt(np.mean(np.square(mono))))
            self.mic_level.emit(rms_to_display_level(rms))

            calibrated = self._vad.feed_calibration_chunk(mono, sample_rate)
            if calibrated is not None:
                self._speech_rms = calibrated.speech_rms
                self._silence_rms = calibrated.silence_rms
                if self._barge is not None:
                    self._barge.set_threshold(self._vad.barge_in_threshold())
                push_activity_line(
                    f"VAD: calibrated speech_rms={self._speech_rms:.4f} "
                    f"silence_rms={self._silence_rms:.4f}"
                )
            else:
                th = self._vad.thresholds
                self._speech_rms = th.speech_rms
                self._silence_rms = th.silence_rms

            if self._session.should_monitor_barge_in() and self._barge is not None:
                if self._barge.check_rms(rms):
                    self._session.on_barge_in_triggered()
                return

            if not self._session.should_accept_capture():
                if in_speech:
                    reset_utterance()
                return

            now = time.time()
            if not in_speech:
                if rms >= self._speech_rms:
                    in_speech = True
                    speech_started_at = now
                    silence_started = None
                    speech_chunks.append(mono.copy())
                    self._session.on_speech_segment_started()
                    self.speech_started.emit()
                return

            speech_chunks.append(mono.copy())
            elapsed = now - speech_started_at
            if elapsed >= max_seconds:
                finalize_utterance()
                return

            if rms < self._silence_rms:
                if silence_started is None:
                    silence_started = now
                elif (now - silence_started) * 1000 >= silence_ms:
                    finalize_utterance()
            else:
                silence_started = None

        stream_kwargs: dict = {
            "channels": 1,
            "samplerate": sample_rate,
            "blocksize": block,
            "callback": callback,
            "dtype": "float32",
            "device": device,
        }

        try:
            with sd.InputStream(**stream_kwargs):
                while self._stream_active.is_set():
                    time.sleep(0.05)
        except Exception as exc:
            self.listen_failed.emit(f"마이크 스트림 오류: {exc}")
            self._stream_active.clear()
