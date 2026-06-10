"""에코 제거 — 플랫폼별 선택 적용, 미설치 시 half-duplex만."""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class EchoCancellationAdapter:
    """AEC 어댑터 — 라이브러리 없으면 passthrough."""

    def __init__(self) -> None:
        self._available = False
        self._processor = None
        self._try_init()

    def _try_init(self) -> None:
        try:
            # webrtc-audio-processing 등 선택 통합 지점
            import webrtc_audio_processing  # type: ignore[import-untyped]  # noqa: F401

            self._available = True
            logger.info("AEC: webrtc-audio-processing 사용 가능")
        except ImportError:
            logger.info("AEC unavailable, half-duplex only")

    @property
    def available(self) -> bool:
        return self._available

    def process_capture(
        self,
        capture: np.ndarray,
        playback_reference: np.ndarray | None = None,
    ) -> np.ndarray:
        """캡처 프레임 처리 — AEC 미가용 시 원본 반환."""
        if not self._available or self._processor is None:
            return capture
        return capture
