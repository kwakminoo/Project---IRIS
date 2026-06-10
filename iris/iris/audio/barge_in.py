"""Barge-in: TTS 중 단일 마이크 스트림에서 RMS 감지 → TTS 중단."""

from __future__ import annotations

import time
from typing import Callable, Optional, Protocol


class TtsStopCapable(Protocol):
    """Barge-in이 호출하는 최소 TTS 인터페이스."""

    def stop(self) -> None: ...


class BargeInMonitor:
    """
    별도 InputStream 없음 — ContinuousListenController 콜백에서 RMS 검사.
    에코 방지: TTS 시작 후 grace_ms 동안 무시.
    """

    def __init__(
        self,
        tts: TtsStopCapable,
        *,
        ui_hook: Optional[Callable[[], None]] = None,
        grace_ms: int = 450,
        threshold: float = 0.02,
    ) -> None:
        self._tts = tts
        self._ui_hook = ui_hook
        self._grace_ms = grace_ms
        self._threshold = threshold
        self._tts_start_ts = 0.0
        self._triggered = False

    def set_threshold(self, threshold: float) -> None:
        self._threshold = max(threshold, 1e-6)

    def notify_tts_started(self) -> None:
        self._tts_start_ts = time.time()
        self._triggered = False

    def reset(self) -> None:
        self._triggered = False

    def check_rms(self, rms: float) -> bool:
        """
        RMS가 임계값 초과 시 TTS 중단.
        반환: barge-in이 발생했으면 True (한 번만).
        """
        if self._triggered:
            return False
        if (time.time() - self._tts_start_ts) * 1000 < self._grace_ms:
            return False
        if rms <= self._threshold:
            return False
        self._triggered = True
        self._tts.stop()
        if self._ui_hook:
            self._ui_hook()
        return True

    def stop(self) -> None:
        """하위 호환 — 별도 스트림 없음."""
        self.reset()


# 하위 호환 별칭
BargeInController = BargeInMonitor
