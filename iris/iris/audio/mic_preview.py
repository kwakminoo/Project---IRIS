"""설정 창 등에서 선택 마이크 입력 레벨만 미리보기."""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from iris.audio.input_device import resolve_input_device
from iris.audio.mic_level import rms_to_display_level


class MicLevelPreview(QObject):
    """백그라운드 InputStream — 레벨 시그널만 방출 (STT/VAD 없음)."""

    level = pyqtSignal(float)
    failed = pyqtSignal(str)

    def __init__(self, sample_rate: int = 16000, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sample_rate = sample_rate
        self._device: int | None = None
        self._thread: Optional[threading.Thread] = None
        self._active = threading.Event()

    def start(self, device: int | None) -> None:
        """지정 장치로 레벨 미리보기를 시작한다."""
        self.stop()
        self._device = device
        self._active.set()
        self._thread = threading.Thread(
            target=self._run,
            name="iris-mic-preview",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._active.clear()

    def _run(self) -> None:
        try:
            import sounddevice as sd
        except Exception:
            self.failed.emit("sounddevice를 사용할 수 없습니다.")
            return

        block = int(self._sample_rate * 0.1)
        device_choice, reason = resolve_input_device(sd, self._device)
        if device_choice is None:
            self.failed.emit(reason)
            return

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if not self._active.is_set():
                return
            mono = np.asarray(indata[:, 0], dtype=np.float32)
            rms = float(np.sqrt(np.mean(np.square(mono))))
            self.level.emit(rms_to_display_level(rms))

        try:
            with sd.InputStream(
                channels=1,
                samplerate=self._sample_rate,
                blocksize=block,
                callback=callback,
                dtype="float32",
                device=device_choice.device,
            ):
                while self._active.is_set():
                    time.sleep(0.05)
        except Exception as exc:
            self.failed.emit(f"마이크 미리보기 오류: {exc}")
