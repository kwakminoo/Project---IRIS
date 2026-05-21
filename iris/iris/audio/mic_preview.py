"""설정 창 등에서 선택 마이크 입력 레벨만 미리보기."""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from iris.audio.input_device import resolve_input_device
from iris.audio.mic_level import rms_to_display_level

# stop() 후 콜백·스레드 join 대기 상한(초)
_STOP_JOIN_TIMEOUT = 2.0


class MicLevelPreview(QObject):
    """백그라운드 InputStream — 레벨 시그널만 방출 (STT/VAD 없음)."""

    level = pyqtSignal(float)
    failed = pyqtSignal(str)

    def __init__(self, sample_rate: int = 16000, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sample_rate = sample_rate
        self._device: int | None = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        # 스트림 루프·콜백 동작 허용
        self._active = threading.Event()
        # Qt 시그널 emit 허용 — stop()에서 가장 먼저 끔
        self._emit_ok = threading.Event()
        # start/stop 세대 — 이전 스트림 콜백이 늦게 도착해도 무시
        self._generation = 0

    def start(self, device: int | None) -> None:
        """지정 장치로 레벨 미리보기를 시작한다."""
        with self._lock:
            self._stop_locked()
            self._generation += 1
            gen = self._generation
            self._device = device
            self._emit_ok.set()
            self._active.set()
            self._thread = threading.Thread(
                target=self._run,
                args=(gen,),
                name="iris-mic-preview",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """미리보기 중단 — 창 닫힌 뒤 콜백이 level.emit 하지 않도록 대기."""
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        # emit 차단을 active 해제보다 먼저 — 레이스 구간 최소화
        self._emit_ok.clear()
        self._active.clear()
        self._generation += 1
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=_STOP_JOIN_TIMEOUT)

    def _safe_emit_level(self, gen: int, value: float) -> None:
        if gen != self._generation:
            return
        if not self._emit_ok.is_set() or not self._active.is_set():
            return
        try:
            self.level.emit(value)
        except RuntimeError:
            # Qt 객체가 이미 삭제된 경우 — 무시
            pass

    def _safe_emit_failed(self, gen: int, message: str) -> None:
        if gen != self._generation:
            return
        if not self._emit_ok.is_set():
            return
        try:
            self.failed.emit(message)
        except RuntimeError:
            pass

    def _run(self, gen: int) -> None:
        try:
            import sounddevice as sd
        except Exception:
            self._safe_emit_failed(gen, "sounddevice를 사용할 수 없습니다.")
            return

        block = int(self._sample_rate * 0.1)
        device_choice, reason = resolve_input_device(sd, self._device)
        if device_choice is None:
            self._safe_emit_failed(gen, reason)
            return

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if gen != self._generation or not self._emit_ok.is_set():
                return
            if not self._active.is_set():
                return
            mono = np.asarray(indata[:, 0], dtype=np.float32)
            rms = float(np.sqrt(np.mean(np.square(mono))))
            self._safe_emit_level(gen, rms_to_display_level(rms))

        try:
            with sd.InputStream(
                channels=1,
                samplerate=self._sample_rate,
                blocksize=block,
                callback=callback,
                dtype="float32",
                device=device_choice.device,
            ):
                while self._active.is_set() and gen == self._generation:
                    time.sleep(0.05)
        except Exception as exc:
            self._safe_emit_failed(gen, f"마이크 미리보기 오류: {exc}")
