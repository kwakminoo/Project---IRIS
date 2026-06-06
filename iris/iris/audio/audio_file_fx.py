"""Apply Iris voice effects to rendered audio files."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np

from iris.audio.voice_fx import apply_voice_fx

_FX_SAMPLE_RATE = 24_000


def apply_voice_fx_to_file(
    input_path: Path,
    output_path: Path,
    fx: dict[str, Any] | None,
    *,
    global_enabled: bool = True,
) -> bool:
    """Decode an audio file, apply voice FX, and write a mono WAV file."""
    if not global_enabled or not fx or not fx.get("enabled", False):
        return False
    try:
        audio = _decode_audio(input_path)
        if audio.size == 0:
            return False
        processed = apply_voice_fx(
            audio,
            fx,
            sample_rate=_FX_SAMPLE_RATE,
            global_enabled=global_enabled,
        )
        _write_wav(output_path, processed, _FX_SAMPLE_RATE)
    except Exception:
        return False
    return output_path.is_file() and output_path.stat().st_size > 0


def _decode_audio(path: Path) -> np.ndarray:
    import av
    from av.audio.resampler import AudioResampler

    chunks: list[np.ndarray] = []
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.array([], dtype=np.float32)
        resampler = AudioResampler(format="s16", layout="mono", rate=_FX_SAMPLE_RATE)
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                arr = resampled.to_ndarray()
                chunks.append(_frame_to_float(arr))

    if not chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32, copy=False)


def _frame_to_float(arr: np.ndarray) -> np.ndarray:
    data = np.asarray(arr)
    if data.ndim > 1:
        data = data.reshape(-1)
    if data.dtype == np.int16:
        return data.astype(np.float32) / 32768.0
    if data.dtype == np.int32:
        return data.astype(np.float32) / 2147483648.0
    return data.astype(np.float32)


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    mono = np.asarray(audio, dtype=np.float32)
    mono = np.clip(mono, -1.0, 1.0)
    pcm = (mono * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
