"""TTS 오디오 길이 측정·추정."""

from __future__ import annotations

import wave
from pathlib import Path

# 한국어 기본 읽기 속도 (tts_speaking_rate=1.0 기준)
_BASE_CHARS_PER_SECOND = 12.0


def audio_file_duration_ms(path: str | Path) -> float | None:
    """WAV/MP3 파일 재생 길이(ms). 실패 시 None."""
    p = Path(path)
    if not p.is_file():
        return None
    suffix = p.suffix.lower()
    if suffix == ".wav":
        try:
            with wave.open(str(p), "rb") as wav:
                rate = wav.getframerate()
                if rate <= 0:
                    return None
                return wav.getnframes() / rate * 1000.0
        except (OSError, wave.Error):
            return None
    if suffix == ".mp3":
        try:
            from pydub import AudioSegment

            return float(len(AudioSegment.from_file(str(p))))
        except Exception:
            return None
    return None


def estimate_speech_duration_ms(text: str, speaking_rate: float = 1.0) -> float:
    """텍스트 길이·말하기 속도로 재생 시간을 추정한다."""
    cleaned = text.strip()
    if not cleaned:
        return 200.0
    rate = max(float(speaking_rate), 0.25)
    chars_per_sec = _BASE_CHARS_PER_SECOND * rate
    return max(300.0, len(cleaned) / chars_per_sec * 1000.0)
