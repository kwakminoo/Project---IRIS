"""로컬 폴백 TTS (pyttsx3)."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from iris.config.settings import Settings


class FallbackTTSEngine:
    """중단 가능한 로컬 TTS (pyttsx3)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.stop()
        except Exception:
            pass

    def speak(
        self,
        text: str,
        on_start: Optional[Callable[[], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """백그라운드 스레드에서 재생."""
        self.stop()
        self._stop.clear()

        def run() -> None:
            if on_start:
                on_start()
            try:
                self._speak_blocking(text)
            finally:
                if on_done:
                    on_done()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _speak_blocking(self, text: str) -> None:
        import pyttsx3

        engine = pyttsx3.init()
        try:
            rate = engine.getProperty("rate")
            engine.setProperty("rate", int(rate * self._settings.tts_speaking_rate))
        except Exception:
            pass
        engine.say(text)
        engine.runAndWait()
