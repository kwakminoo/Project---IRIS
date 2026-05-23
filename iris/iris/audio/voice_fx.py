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
    wet = np.zeros_like(audio)
    for delay_ms, gain in ((18, 0.28), (36, 0.16)):
        delay = int(sample_rate * delay_ms / 1000)
        if 0 < delay < len(audio):
            wet[delay:] += audio[:-delay] * gain
    return np.clip(audio * (1.0 - amount * 0.10) + wet * amount, -1.0, 1.0)


def _subtle_chorus(audio: np.ndarray, amount: float, sample_rate: int = 24000) -> np.ndarray:
    """아주 약한 이중화 느낌."""
    if amount <= 0 or audio.size < 4:
        return audio
    out = audio * (1.0 - amount * 0.18)
    for shift_ms, gain in ((3.5, 0.38), (7.0, 0.22)):
        shift = max(1, int(sample_rate * shift_ms / 1000))
        delayed = np.zeros_like(audio)
        delayed[shift:] = audio[:-shift]
        out += delayed * amount * gain
    return np.clip(out, -1.0, 1.0)


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


def _warm_body(audio: np.ndarray, amount: float = 0.08) -> np.ndarray:
    """Add a small amount of low-mid body without changing the voice model."""
    if amount <= 0 or audio.size < 3:
        return audio
    body = np.copy(audio)
    body[1:] = body[:-1] * 0.62 + body[1:] * 0.38
    body[2:] = body[:-2] * 0.28 + body[2:] * 0.72
    return np.clip(audio * (1.0 - amount * 0.18) + body * amount * 0.42, -1.0, 1.0)


def _soften_brightness(audio: np.ndarray, amount: float = 0.08) -> np.ndarray:
    """Reduce overly bright assistant/phone-guide sharpness."""
    if amount <= 0 or audio.size < 2:
        return audio
    softened = np.copy(audio)
    softened[1:] = softened[:-1] * 0.35 + softened[1:] * 0.65
    return np.clip(audio * (1.0 - amount) + softened * amount, -1.0, 1.0)


def _ai_resonance(audio: np.ndarray, amount: float = 0.18, sample_rate: int = 24000) -> np.ndarray:
    """Add a clean synthetic assistant resonance without noisy distortion."""
    if amount <= 0 or audio.size < 4:
        return audio
    out = audio * (1.0 - amount * 0.10)
    for delay_ms, gain in ((4.0, 0.20), (8.0, -0.12)):
        shift = max(1, int(sample_rate * delay_ms / 1000))
        delayed = np.zeros_like(audio)
        delayed[shift:] = audio[:-shift]
        out += delayed * amount * gain
    return np.clip(out, -1.0, 1.0)


def _robotic_texture(audio: np.ndarray, amount: float, sample_rate: int = 24000) -> np.ndarray:
    """아주 약한 링 변조 질감."""
    if amount <= 0 or audio.size == 0:
        return audio
    t = np.arange(len(audio), dtype=np.float32) / float(sample_rate)
    carrier_low = np.sin(2.0 * np.pi * 44.0 * t).astype(np.float32)
    carrier_high = np.sin(2.0 * np.pi * 88.0 * t).astype(np.float32)
    shimmer = np.sin(2.0 * np.pi * 176.0 * t).astype(np.float32)
    movement = 0.90 + 0.10 * np.sin(2.0 * np.pi * 8.0 * t).astype(np.float32)
    ring = audio * (carrier_low * 0.46 + carrier_high * 0.30 + shimmer * 0.10)
    modulated = (audio * (1.0 - amount * 0.22) + ring * amount * 0.30) * movement
    return np.clip(modulated, -1.0, 1.0)


def _smooth_edges(audio: np.ndarray, sample_rate: int = 24000) -> np.ndarray:
    """Avoid clicks at the start/end of generated speech files."""
    if audio.size < 8:
        return audio
    a = np.array(audio, dtype=np.float32, copy=True)
    fade_len = min(a.size // 4, max(1, int(sample_rate * 0.018)))
    fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
    fade_out = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    a[:fade_len] *= fade_in
    a[-fade_len:] *= fade_out
    return a


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

    a = _smooth_edges(a, sample_rate)
    a = _low_cut(a, 0.08)
    a = _warm_body(a, 0.13)
    a = _soften_brightness(a, 0.10)
    a = _soft_reverb(a, reverb, sample_rate)
    a = _subtle_chorus(a, chorus, sample_rate)
    a = _high_presence(a, presence)
    a = _robotic_texture(a, robotic, sample_rate)
    a = _ai_resonance(a, float(fx.get("ai_resonance", 0.22)), sample_rate)
    a = _soften_brightness(a, 0.10)
    return _smooth_edges(_ensure_mono_float(a), sample_rate)
