"""VAD 캘리브레이션 — 노이즈 플로어 기반 임계값."""

import numpy as np
from dataclasses import replace

from iris.audio.vad_calibrator import VadCalibrator, compute_vad_thresholds, rms_of
from iris.config.settings import load_settings


def test_rms_of_silence_near_zero() -> None:
    samples = np.zeros(1600, dtype=np.float32)
    assert rms_of(samples) < 1e-6


def test_compute_vad_thresholds_from_noise() -> None:
    noise = np.full(1600, 0.004, dtype=np.float32)
    th = compute_vad_thresholds(noise, speech_multiplier=2.5, silence_multiplier=1.3)
    assert abs(th.noise_floor_rms - 0.004) < 1e-5
    assert abs(th.speech_rms - 0.01) < 1e-5
    assert abs(th.silence_rms - 0.0052) < 1e-5


def test_calibrator_feed_completes_after_two_seconds() -> None:
    settings = replace(
        load_settings(),
        voice_vad_auto_calibrate=True,
        always_listen_speech_rms_manual=False,
        voice_speech_rms_multiplier=2.5,
        voice_silence_rms_multiplier=1.3,
    )
    cal = VadCalibrator(settings)
    sr = 16000
    chunk = np.full(int(sr * 0.1), 0.005, dtype=np.float32)
    result = None
    for _ in range(25):
        result = cal.feed_calibration_chunk(chunk, sr)
        if result is not None:
            break
    assert result is not None
    assert result.speech_rms > result.silence_rms
