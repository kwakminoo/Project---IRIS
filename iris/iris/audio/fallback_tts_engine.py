"""Edge-tts / pyttsx3 폴백 TTS (XTTS 실패·미설치 시)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from iris.audio.tts_edge import EdgeTTSEngine
from iris.audio.tts_fallback import FallbackTTSEngine as Pyttsx3Engine
from iris.config.settings import Settings


class FallbackTTSEngine:
    """
    TTS_FALLBACK_PROVIDER에 따라 edge-tts 또는 pyttsx3를 사용한다.

    edge: MP3 파일 합성 (재생은 AudioPlayer)
    pyttsx3: 동기 재생 (on_start/on_done 콜백 지원)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._edge = EdgeTTSEngine(settings)
        self._pyttsx3 = Pyttsx3Engine(settings)

    @property
    def provider(self) -> str:
        p = self._settings.tts_fallback_provider
        if p in {"edge", "microsoft", "azure"}:
            return "edge"
        return "pyttsx3"

    def render_to_file_sync(self, text: str, out_path: Path) -> bool:
        """edge 폴백: MP3 파일 생성."""
        if self.provider != "edge":
            return False
        return self._edge.render_to_file_sync(text, out_path)

    def speak_blocking(
        self,
        text: str,
        *,
        on_start: Optional[Callable[[], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """pyttsx3 폴백: 블로킹 재생."""
        self._pyttsx3.speak(text, on_start=on_start, on_done=on_done)

    def stop(self) -> None:
        self._pyttsx3.stop()
