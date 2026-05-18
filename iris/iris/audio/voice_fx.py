"""TTS 후처리 — 자비스 스타일 약한 공간감·질감 (선택 적용)."""

from __future__ import annotations

from typing import Any

import numpy as np

# 사람 목소리 80% / AI 질감 20% 목표 — 기본값은 약하게 유지


def _ensure_mono_float(audio: np.ndarray) -> np.ndarray:
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim > 1:
        a = a.mean(axis=1)
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak > 1.0:
        a = a / peak
    return a


def _soft_reverb(audio: np.ndarray, amount: float, sample_rate: int = 24000) -> np.ndarray:
    """짧은 딜레이 믹스로 부드러운 잔향."""
    if amount <= 0 or audio.size == 0:
        return audio
    delay = int(sample_rate * 0.028)
    if delay >= len(audio):
        return audio
    wet = np.zeros_like(audio)
    wet[delay:] = audio[:-delay] * 0.55
    return audio * (1.0 - amount * 0.35) + wet * amount


def _subtle_chorus(audio: np.ndarray, amount: float, sample_rate: int = 24000) -> np.ndarray:
    """아주 약한 이중화 느낌."""
    if amount <= 0 or audio.size < 4:
        return audio
    shift = max(1, int(sample_rate * 0.003))
    delayed = np.zeros_like(audio)
    delayed[shift:] = audio[:-shift]
    return audio * (1.0 - amount * 0.25) + delayed * amount * 0.4


def _high_presence(audio: np.ndarray, amount: float = 0.06) -> np.ndarray:
    """고역 살짝 강조 (1차 차분 근사)."""
    if amount <= 0 or audio.size < 2:
        return audio
    diff = np.zeros_like(audio)
    diff[1:] = audio[1:] - audio[:-1]
    return np.clip(audio + diff * amount * 2.5, -1.0, 1.0)


def _low_cut(audio: np.ndarray, amount: float = 0.12) -> np.ndarray:
    """저역 약하게 감쇠."""
    if amount <= 0 or audio.size < 2:
        return audio
    smoothed = np.copy(audio)
    smoothed[1:] = (smoothed[:-1] + smoothed[1:]) * 0.5
    return audio * (1.0 - amount * 0.3) + smoothed * amount * 0.3


def _robotic_texture(audio: np.ndarray, amount: float, sample_rate: int = 24000) -> np.ndarray:
    """아주 약한 링 변조 질감."""
    if amount <= 0 or audio.size == 0:
        return audio
    t = np.arange(len(audio), dtype=np.float32) / float(sample_rate)
    carrier = np.sin(2.0 * np.pi * 90.0 * t).astype(np.float32)
    modulated = audio * (1.0 - amount * 0.15) + (audio * carrier) * amount * 0.12
    return np.clip(modulated, -1.0, 1.0)


def apply_voice_fx(
    audio: np.ndarray,
    fx: dict[str, Any] | None,
    *,
    sample_rate: int = 24000,
    global_enabled: bool = True,
) -> np.ndarray:
    """
    프리셋 fx 블록을 적용한다.

    fx 예: {"enabled": true, "reverb": 0.08, "chorus": 0.04, "robotic_texture": 0.03}
    """
    if not global_enabled or not fx or not fx.get("enabled", False):
        return _ensure_mono_float(audio)

    a = _ensure_mono_float(audio)
    reverb = float(fx.get("reverb", 0.08))
    chorus = float(fx.get("chorus", 0.04))
    robotic = float(fx.get("robotic_texture", 0.03))
    presence = float(fx.get("presence", 0.06))

    a = _low_cut(a, 0.12)
    a = _soft_reverb(a, reverb, sample_rate)
    a = _subtle_chorus(a, chorus, sample_rate)
    a = _high_presence(a, presence)
    a = _robotic_texture(a, robotic, sample_rate)
    return _ensure_mono_float(a)
