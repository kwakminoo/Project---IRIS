"""STT (faster-whisper)."""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from iris.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SttSegment:
    """세그먼트 메타 — 테스트·디버그용."""

    text: str
    no_speech_prob: float
    avg_logprob: float
    compression_ratio: float


@dataclass
class SttResult:
    text: str | None
    no_speech: bool
    confidence: float
    segments: list[SttSegment] = field(default_factory=list)
    reject_reason: str = ""


def build_stt_initial_prompt(settings: Settings) -> str:
    """호출어 힌트만 제공 — 설명형 문장 제거."""
    custom = (settings.stt_initial_prompt or "").strip()
    if custom:
        return custom[:80]
    words = ", ".join(settings.voice_wake_words) if settings.voice_wake_words else "아이리스, iris, 이리스"
    return words[:80]


def evaluate_stt_result(
    segments: list[SttSegment],
    *,
    no_speech_threshold: float,
    min_avg_logprob: float,
) -> SttResult:
    """Whisper 세그먼트 메타데이터로 no-speech 판정."""
    if not segments:
        return SttResult(
            text=None,
            no_speech=True,
            confidence=0.0,
            segments=[],
            reject_reason="no_segments",
        )

    avg_no_speech = sum(s.no_speech_prob for s in segments) / len(segments)
    avg_logprob = sum(s.avg_logprob for s in segments) / len(segments)
    text = " ".join(s.text for s in segments).strip() or None

    if avg_no_speech >= no_speech_threshold:
        return SttResult(
            text=None,
            no_speech=True,
            confidence=avg_logprob,
            segments=segments,
            reject_reason=f"no_speech_prob={avg_no_speech:.3f}",
        )
    if avg_logprob < min_avg_logprob:
        return SttResult(
            text=None,
            no_speech=True,
            confidence=avg_logprob,
            segments=segments,
            reject_reason=f"low_logprob={avg_logprob:.3f}",
        )

    return SttResult(
        text=text,
        no_speech=False,
        confidence=avg_logprob,
        segments=segments,
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

    def _segment_from_raw(self, raw: Any) -> SttSegment:
        return SttSegment(
            text=(raw.text or "").strip(),
            no_speech_prob=float(getattr(raw, "no_speech_prob", 0.0) or 0.0),
            avg_logprob=float(getattr(raw, "avg_logprob", 0.0) or 0.0),
            compression_ratio=float(getattr(raw, "compression_ratio", 0.0) or 0.0),
        )

    def _transcribe_with_loaded_model(self, samples: np.ndarray) -> SttResult:
        prompt = build_stt_initial_prompt(self._settings)
        segments_iter, _info = self._model.transcribe(  # type: ignore[union-attr]
            samples.astype(np.float32),
            language="ko",
            vad_filter=self._settings.stt_vad_filter,
            beam_size=self._settings.stt_beam_size,
            initial_prompt=prompt,
            condition_on_previous_text=self._settings.stt_condition_on_previous_text,
        )
        segments = [self._segment_from_raw(s) for s in segments_iter]
        return evaluate_stt_result(
            segments,
            no_speech_threshold=self._settings.stt_no_speech_threshold,
            min_avg_logprob=self._settings.stt_min_avg_logprob,
        )

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> SttResult:
        """float32 모노 PCM → SttResult."""
        if not self._ensure_model() or self._model is False:
            return SttResult(
                text=None,
                no_speech=True,
                confidence=0.0,
                reject_reason="model_unavailable",
            )
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
            return SttResult(
                text=None,
                no_speech=True,
                confidence=0.0,
                reject_reason="transcribe_error",
            )

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        """하위 호환 — no_speech이면 None."""
        result = self.transcribe(samples, sample_rate)
        if result.no_speech or not result.text:
            return None
        return result.text
