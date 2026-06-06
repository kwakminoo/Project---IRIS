"""Short UI sound effects for Iris state changes."""

from __future__ import annotations

import math
import os
import tempfile
import wave
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QObject, QUrl

try:
    from PyQt6.QtMultimedia import QSoundEffect

    _SOUND_EFFECT_AVAILABLE = True
except ImportError:  # pragma: no cover
    QSoundEffect = None  # type: ignore[misc, assignment]
    _SOUND_EFFECT_AVAILABLE = False

from iris.core.state_machine import AppState

_SAMPLE_RATE = 44_100
_MASTER_VOLUME = 0.52
_MIN_INTERVAL_MS = 120
_CUE_VERSION = "mechanical_relay_v2"


class SystemSoundPlayer(QObject):
    """Generate and play tiny sci-fi style cues without bundled audio files."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._enabled = os.getenv("IRIS_ENABLE_SYSTEM_SOUNDS", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        self._last_play_ms = 0
        self._last_cue = ""
        self._effects: dict[str, QSoundEffect] = {}
        self._paths: dict[str, Path] = {}
        if self._enabled and _SOUND_EFFECT_AVAILABLE:
            self._prepare()

    def play_state(self, state: AppState, now_ms: int) -> None:
        """Play a short cue for meaningful active states."""
        if not self._enabled or not _SOUND_EFFECT_AVAILABLE:
            return
        cue = {
            AppState.PROCESSING: "processing",
            AppState.RESPONDING: "respond",
            AppState.EXECUTING: "execute",
        }.get(state)
        if cue is None:
            return
        if cue == self._last_cue and now_ms - self._last_play_ms < _MIN_INTERVAL_MS:
            return
        effect = self._effects.get(cue)
        if effect is None:
            return
        self._last_play_ms = now_ms
        self._last_cue = cue
        effect.play()

    def _prepare(self) -> None:
        temp_dir = Path(tempfile.gettempdir()) / "iris_system_sounds"
        temp_dir.mkdir(parents=True, exist_ok=True)

        cues = {
            "idle": [(260, 210, 0.055, 0.34), (1260, 1080, 0.03, 0.20)],
            "listen": [(320, 250, 0.075, 0.58), (980, 820, 0.045, 0.34), (1820, 1560, 0.026, 0.20)],
            "processing": [(1450, 1450, 0.026, 0.50), (320, 320, 0.036, 0.54), (2450, 2450, 0.018, 0.28)],
            "execute": [(1180, 1180, 0.03, 0.56), (260, 260, 0.052, 0.68), (2880, 2880, 0.018, 0.34)],
            "respond": [(1450, 1450, 0.026, 0.50), (320, 320, 0.036, 0.54), (2450, 2450, 0.018, 0.28)],
            "alert": [(420, 720, 0.07, 0.66), (1580, 1380, 0.04, 0.32)],
            "error": [(230, 150, 0.13, 0.62), (900, 620, 0.055, 0.26)],
        }

        for name, notes in cues.items():
            path = temp_dir / f"{name}_{_CUE_VERSION}.wav"
            _write_tone_sequence(path, notes)
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(str(path)))
            effect.setLoopCount(1)
            effect.setVolume(_MASTER_VOLUME)
            self._paths[name] = path
            self._effects[name] = effect


def _write_tone_sequence(path: Path, notes: Iterable[tuple[float, float, float, float]]) -> None:
    samples: list[int] = []
    gap = int(_SAMPLE_RATE * 0.006)
    for start_freq, end_freq, duration, gain in notes:
        samples.extend(_tone_sweep(start_freq, end_freq, duration, gain))
        samples.extend([0] * gap)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(b"".join(int(s).to_bytes(2, "little", signed=True) for s in samples))


def _tone_sweep(start_freq: float, end_freq: float, duration: float, gain: float) -> list[int]:
    count = max(1, int(_SAMPLE_RATE * duration))
    out: list[int] = []
    phase = 0.0
    for i in range(count):
        progress = i / max(1, count - 1)
        stepped = int(progress * 5.0) / 5.0
        freq = start_freq + (end_freq - start_freq) * stepped
        phase += 2.0 * math.pi * freq / _SAMPLE_RATE
        env = _envelope(i, count)
        gate = 1.0 if int(progress * 12.0) % 2 == 0 else 0.62
        metallic = math.sin(phase * 3.71) * 0.18
        relay = math.sin(phase * 6.13) * 0.08
        low_body = math.sin(phase * 0.5) * 0.10
        wave_value = (math.sin(phase) * 0.48 + metallic + relay + low_body) * gate
        out.append(int(max(-1.0, min(1.0, wave_value * env * gain)) * 12_000))
    return out


def _envelope(index: int, total: int) -> float:
    attack = max(1, int(total * 0.025))
    release = max(1, int(total * 0.52))
    if index < attack:
        return index / attack
    remaining = total - index
    if remaining < release:
        return max(0.0, remaining / release)
    return 1.0
