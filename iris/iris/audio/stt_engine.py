"""STT (faster-whisper)."""

from __future__ import annotations

from typing import Optional

import numpy as np

from iris.config.settings import Settings


def build_stt_initial_prompt(settings: Settings) -> str:
    """호출어·자주 쓰는 단어를 Whisper에 힌트로 제공."""
    custom = (settings.stt_initial_prompt or "").strip()
    if custom:
        return custom
    words = ", ".join(settings.voice_wake_words) if settings.voice_wake_words else "아이리스, iris, 이리스"
    return (
        f"호출어와 명령: {words}. "
        "한국어 음성 비서 Iris. 사용자가 아이리스라고 부르면 아이리스로 받아적는다."
    )


def resolve_stt_device_compute(settings: Settings) -> tuple[str, str]:
    """device / compute_type 결정 (auto 시 CUDA 가능하면 사용)."""
    device = settings.stt_device.strip().lower()
    compute = settings.stt_compute_type.strip().lower()

    if device == "auto":
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", compute if compute not in ("", "auto") else "float16"
        except Exception:
            pass
        return "cpu", compute if compute not in ("", "auto") else "int8"

    if device == "cuda":
        return "cuda", compute if compute not in ("", "auto") else "float16"
    return "cpu", compute if compute not in ("", "auto") else "int8"


class SttEngine:
    """faster-whisper. 실패 시 None."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._loaded_device: str | None = None

    def warmup(self) -> None:
        """앱 시작 시 모델 선로딩."""
        self._ensure_model()

    def _ensure_model(self) -> bool:
        if not self._settings.use_whisper:
            return False
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel

            device, compute_type = resolve_stt_device_compute(self._settings)
            self._model = WhisperModel(
                self._settings.stt_model,
                device=device,
                compute_type=compute_type,
            )
            self._loaded_device = device
            return True
        except Exception:
            self._model = False  # type: ignore[assignment]
            return False

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        """float32 모노 PCM."""
        if not self._ensure_model() or self._model is False:
            return None
        try:
            prompt = build_stt_initial_prompt(self._settings)
            segments, _info = self._model.transcribe(  # type: ignore[union-attr]
                samples.astype(np.float32),
                language="ko",
                vad_filter=self._settings.stt_vad_filter,
                beam_size=self._settings.stt_beam_size,
                initial_prompt=prompt,
            )
            parts = [s.text for s in segments]
            text = " ".join(parts).strip()
            return text or None
        except Exception:
            return None
