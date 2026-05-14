"""STT (faster-whisper 구조)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from iris.config.settings import Settings


class SttEngine:
    """옵션 faster-whisper. 실패 시 transcribe None."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None

    def _ensure_model(self) -> bool:
        if not self._settings.use_whisper:
            return False
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self._settings.stt_model, device="cpu", compute_type="int8")
            return True
        except Exception:
            self._model = False  # type: ignore[assignment]
            return False

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        """float32 모노 PCM."""
        if not self._ensure_model() or self._model is False:
            return None
        try:
            segments, _info = self._model.transcribe(  # type: ignore[union-attr]
                samples.astype(np.float32),
                language="ko",
                vad_filter=True,
            )
            parts = [s.text for s in segments]
            text = " ".join(parts).strip()
            return text or None
        except Exception:
            return None
