"""STT (faster-whisper)."""

from __future__ import annotations

import ctypes
import logging
from typing import Optional

import numpy as np

from iris.config.settings import Settings

logger = logging.getLogger(__name__)


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


def cuda_runtime_ready() -> bool:
    """
    ctranslate2 CUDA 카운트만으로는 부족함.
    cuBLAS DLL이 없으면 transcribe가 멈추거나 실패함 (Windows에서 흔함).
    """
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return False
    except Exception:
        return False
    for dll in ("cublas64_12.dll", "cublas64_11.dll"):
        try:
            ctypes.CDLL(dll)
            return True
        except OSError:
            continue
    return False


def resolve_stt_device_compute(settings: Settings) -> tuple[str, str]:
    """device / compute_type 결정 (auto 시 CUDA 런타임 사용 가능할 때만)."""
    device = settings.stt_device.strip().lower()
    compute = settings.stt_compute_type.strip().lower()

    want_cuda = device in ("auto", "cuda")
    if want_cuda and cuda_runtime_ready():
        return "cuda", compute if compute not in ("", "auto") else "float16"
    if want_cuda and device == "cuda":
        logger.warning(
            "STT_DEVICE=cuda 이지만 cuBLAS를 로드할 수 없어 CPU로 STT를 실행합니다."
        )
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

    def _reset_model(self) -> None:
        self._model = None
        self._loaded_device = None

    def _load_model(self, device: str, compute_type: str) -> bool:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self._settings.stt_model,
            device=device,
            compute_type=compute_type,
        )
        self._loaded_device = device
        return True

    def _ensure_model(self) -> bool:
        if not self._settings.use_whisper:
            return False
        if self._model is not None:
            return True
        device, compute_type = resolve_stt_device_compute(self._settings)
        try:
            return self._load_model(device, compute_type)
        except Exception as exc:
            logger.warning("STT 모델 로드 실패 (%s/%s): %s", device, compute_type, exc)
            if device == "cuda":
                try:
                    logger.warning("STT CPU 폴백으로 재시도합니다.")
                    return self._load_model("cpu", "int8")
                except Exception as cpu_exc:
                    logger.warning("STT CPU 폴백 로드 실패: %s", cpu_exc)
            self._model = False  # type: ignore[assignment]
            return False

    def _transcribe_with_loaded_model(self, samples: np.ndarray) -> Optional[str]:
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

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        """float32 모노 PCM."""
        if not self._ensure_model() or self._model is False:
            return None
        try:
            return self._transcribe_with_loaded_model(samples)
        except Exception as exc:
            logger.warning("STT transcribe 실패 (%s): %s", self._loaded_device, exc)
            if self._loaded_device == "cuda":
                self._reset_model()
                try:
                    if self._load_model("cpu", "int8"):
                        return self._transcribe_with_loaded_model(samples)
                except Exception as cpu_exc:
                    logger.warning("STT CPU 폴백 transcribe 실패: %s", cpu_exc)
            return None
