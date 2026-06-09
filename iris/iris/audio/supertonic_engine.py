"""Supertonic 3 local TTS integration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings

# HF Space 표시명 → SDK 코드 (https://huggingface.co/spaces/Supertone/supertonic-3)
_SUPERTONIC_VOICE_ALIASES: dict[str, str] = {
    "alex": "M1",
    "james": "M2",
    "robert": "M3",
    "sam": "M4",
    "daniel": "M5",
    "sarah": "F1",
    "lily": "F2",
    "jessica": "F3",
    "olivia": "F4",
    "emily": "F5",
}
_SUPERTONIC_VOICE_CODES = {*(f"M{i}" for i in range(1, 6)), *(f"F{i}" for i in range(1, 6))}


def resolve_supertonic_voice_name(raw: str) -> str:
    """표시 이름(Lily) 또는 코드(F2)를 Supertonic SDK voice_name으로 정규화."""
    key = (raw or "Lily").strip()
    if not key:
        return "F2"
    code = key.upper()
    if code in _SUPERTONIC_VOICE_CODES:
        return code
    alias = _SUPERTONIC_VOICE_ALIASES.get(key.lower())
    if alias:
        return alias
    return code


class SupertonicEngine:
    """Small wrapper around the optional Supertonic Python SDK."""

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._tts = None
        self._voice_style = None
        self._load_error: str | None = None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def is_available(self) -> bool:
        return self._ensure_loaded()

    def synthesize_to_wav(self, text: str, out_path: Path, *, speed: float = 1.0) -> bool:
        """Render text to a WAV file using Supertonic 3."""
        if not self._ensure_loaded():
            return False
        try:
            wav, _duration = self._tts.synthesize(
                text=text,
                lang=self._settings.supertonic_language,
                voice_style=self._voice_style,
                total_steps=self._settings.supertonic_total_steps,
                speed=max(0.7, min(2.0, speed)),
            )
            self._tts.save_audio(wav, str(out_path))
        except Exception as exc:
            self._load_error = str(exc)
            return False
        return out_path.is_file() and out_path.stat().st_size > 0

    def _ensure_loaded(self) -> bool:
        if self._tts is not None and self._voice_style is not None:
            return True
        try:
            from supertonic import TTS

            self._tts = TTS(auto_download=True)
            voice_code = resolve_supertonic_voice_name(self._settings.supertonic_voice)
            self._voice_style = self._tts.get_voice_style(voice_name=voice_code)
            self._load_error = None
            return True
        except Exception as exc:
            self._load_error = str(exc)
            self._tts = None
            self._voice_style = None
            return False
