"""상시 음성 대기: 에너지 VAD로 발화 구간을 잡고 STT 후 시그널로 전달."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from iris.audio.input_device import resolve_input_device
from iris.audio.mic_level import rms_to_display_level

if TYPE_CHECKING:
    from iris.audio.stt_engine import SttEngine
    from iris.config.settings import Settings


class ContinuousListenController(QObject):
    """
    백그라운드 마이크 스트림 + RMS VAD.
    TTS/LLM 처리 중에는 pause()로 수집을 막아 스피커 에코를 줄인다.
    """

    utterance_ready = pyqtSignal(str)
    utterance_failed = pyqtSignal()  # STT 결과 없음
    listen_failed = pyqtSignal(str)
    mic_level = pyqtSignal(float)
    speech_started = pyqtSignal()
    stt_started = pyqtSignal()  # 침묵 확정 후 Whisper 변환 시작

    def __init__(self, settings: "Settings", stt: "SttEngine", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._stt = stt
        self._thread: Optional[threading.Thread] = None
        self._stream_active = threading.Event()
        self._accept_audio = threading.Event()
        self._accept_audio.set()

    def start(self) -> None:
        """상시 듣기 스레드 시작."""
        if self._thread and self._thread.is_alive():
            self._accept_audio.set()
            return
        self._stream_active.set()
        self._accept_audio.set()
        self._thread = threading.Thread(target=self._run_loop, name="iris-continuous-listen", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        """처리/TTS 중 — 새 발화 수집 중단."""
        self._accept_audio.clear()

    def resume(self) -> None:
        """대화 가능 상태로 복귀."""
        self._accept_audio.set()

    def stop(self) -> None:
        self._stream_active.clear()
        self._accept_audio.clear()

    def _transcribe_and_emit(self, audio: np.ndarray, sample_rate: int) -> None:
        text = self._stt.transcribe_audio(audio, sample_rate)
        if text:
            self.utterance_ready.emit(text.strip())
        else:
            self.utterance_failed.emit()

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
        speech_rms = self._settings.always_listen_speech_rms
        silence_rms = self._settings.always_listen_silence_rms
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
            self.stt_started.emit()
            # STT는 무거우므로 오디오 콜백을 막지 않도록 별도 스레드에서 실행
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
            rms = float(np.sqrt(np.mean(np.square(mono))))
            self.mic_level.emit(rms_to_display_level(rms))

            if not self._accept_audio.is_set():
                if in_speech:
                    reset_utterance()
                return

            now = time.time()
            if not in_speech:
                if rms >= speech_rms:
                    in_speech = True
                    speech_started_at = now
                    silence_started = None
                    speech_chunks.append(mono.copy())
                    self.speech_started.emit()
                return

            speech_chunks.append(mono.copy())
            elapsed = now - speech_started_at
            if elapsed >= max_seconds:
                finalize_utterance()
                return

            if rms < silence_rms:
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
