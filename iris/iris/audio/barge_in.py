"""Barge-in: TTS 중 마이크 입력 감지 시 TTS 중단."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import numpy as np

from iris.audio.tts_engine import TtsEngine


class BargeInController:
    """
    TTS 재생 중 RMS가 임계값을 넘으면 TTS 중단 후 UI 훅 호출.
    에코 방지: TTS 시작 후 grace_ms 동안 무시.
    """

    def __init__(
        self,
        tts: TtsEngine,
        ui_hook: Optional[Callable[[], None]] = None,
        grace_ms: int = 450,
        threshold: float = 0.02,
    ) -> None:
        self._tts = tts
        self._ui_hook = ui_hook
        self._grace_ms = grace_ms
        self._threshold = threshold
        self._thread: Optional[threading.Thread] = None
        self._active = threading.Event()
        self._tts_start_ts = 0.0

    def notify_tts_started(self) -> None:
        self._tts_start_ts = time.time()

    def start_listening(self) -> None:
        self.stop()
        self._active.set()

        def loop() -> None:
            try:
                import sounddevice as sd
            except Exception:
                return
            sample_rate = 16000
            block = int(sample_rate * 0.2)

            def callback(indata, frames, time_info, status):  # noqa: ARG001
                if not self._active.is_set():
                    return
                if (time.time() - self._tts_start_ts) * 1000 < self._grace_ms:
                    return
                rms = float(np.sqrt(np.mean(np.square(indata))))
                if rms > self._threshold:
                    self._tts.stop()
                    self._active.clear()
                    if self._ui_hook:
                        self._ui_hook()

            try:
                with sd.InputStream(
                    channels=1,
                    samplerate=sample_rate,
                    blocksize=block,
                    callback=callback,
                ):
                    while self._active.is_set():
                        time.sleep(0.05)
            except Exception:
                self._active.clear()

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._active.clear()
