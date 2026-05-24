"""Supertonic 3 local TTS integration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings


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
            self._voice_style = self._tts.get_voice_style(
                voice_name=self._settings.supertonic_voice
            )
            self._load_error = None
            return True
        except Exception as exc:
            self._load_error = str(exc)
            self._tts = None
            self._voice_style = None
            return False
