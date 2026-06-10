"""VAD 임계값 캘리브레이션 — 노이즈 플로어 기반."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from iris.config.settings import Settings


@dataclass(frozen=True)
class VadThresholds:
    noise_floor_rms: float
    speech_rms: float
    silence_rms: float


def rms_of(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))


def compute_vad_thresholds(
    noise_samples: np.ndarray,
    *,
    speech_multiplier: float,
    silence_multiplier: float,
) -> VadThresholds:
    """노이즈 샘플 RMS → speech/silence 임계값."""
    floor = max(rms_of(noise_samples), 1e-6)
    return VadThresholds(
        noise_floor_rms=floor,
        speech_rms=floor * speech_multiplier,
        silence_rms=floor * silence_multiplier,
    )


class VadCalibrator:
    """설정 또는 시작 시 노이즈 측정으로 VAD 임계값 산출."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._noise_buffer: list[np.ndarray] = []
        self._calibrated: VadThresholds | None = None
        self._calibration_seconds = 2.0

    @property
    def is_manual_override(self) -> bool:
        return self._settings.always_listen_speech_rms_manual

    @property
    def thresholds(self) -> VadThresholds:
        if self._calibrated is not None:
            return self._calibrated
        return VadThresholds(
            noise_floor_rms=self._settings.always_listen_silence_rms / self._settings.voice_silence_rms_multiplier,
            speech_rms=self._settings.always_listen_speech_rms,
            silence_rms=self._settings.always_listen_silence_rms,
        )

    def should_collect_calibration(self) -> bool:
        if self.is_manual_override:
            return False
        if not self._settings.voice_vad_auto_calibrate:
            return False
        return self._calibrated is None

    def feed_calibration_chunk(self, mono: np.ndarray, sample_rate: int) -> VadThresholds | None:
        """캘리브레이션 중 청크 누적 — 완료 시 임계값 반환."""
        if not self.should_collect_calibration():
            return None
        self._noise_buffer.append(mono.copy())
        total_samples = sum(c.size for c in self._noise_buffer)
        if total_samples < int(sample_rate * self._calibration_seconds):
            return None
        merged = np.concatenate(self._noise_buffer, axis=0)
        self._calibrated = compute_vad_thresholds(
            merged,
            speech_multiplier=self._settings.voice_speech_rms_multiplier,
            silence_multiplier=self._settings.voice_silence_rms_multiplier,
        )
        self._noise_buffer.clear()
        return self._calibrated

    def barge_in_threshold(self) -> float:
        """barge-in RMS = noise_floor × multiplier."""
        th = self.thresholds
        return th.noise_floor_rms * self._settings.barge_in_rms_multiplier
