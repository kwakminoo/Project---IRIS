"""TTS 레거시 진입점 — TTSManager에 위임."""

from __future__ import annotations

from typing import Callable, Optional

from iris.audio.audio_player import AudioPlayer
from iris.audio.tts_manager import TTSManager
from iris.config.settings import Settings


class TtsEngine(TTSManager):
    """하위 호환용 별칭 (speak(on_start=...) 시그니처 유지)."""

    def __init__(
        self,
        settings: Settings,
        playback_bridge: AudioPlayer | None = None,
        parent=None,
    ) -> None:
        # AudioPlayer 부모는 TTSManager여야 playback_gen 검사가 동작한다.
        super().__init__(settings, player=playback_bridge, parent=parent)
        if playback_bridge is not None and playback_bridge.parent() is not parent:
            playback_bridge.setParent(self)

    def speak(
        self,
        text: str,
        on_start: Callable[[], None] | None = None,
        on_done: Callable[[], None] | None = None,
        mode: str = "normal",
        on_synthesis_start: Callable[[], None] | None = None,
        on_playback_start: Callable[[], None] | None = None,
    ) -> None:
        super().speak(
            text,
            mode=mode,
            on_synthesis_start=on_synthesis_start,
            on_playback_start=on_playback_start or on_start,
            on_done=on_done,
        )
