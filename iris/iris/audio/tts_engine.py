"""TTS: Edge(기본) + pyttsx3 폴백, 추후 로컬 엔진 교체 가능한 얇은 구조."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QMetaObject, Qt, pyqtSlot

from iris.audio.tts_edge import EdgeTTSEngine
from iris.audio.tts_fallback import FallbackTTSEngine
from iris.config.settings import Settings
from iris.audio.tts_qt_playback import EdgeTtsPlaybackBridge


class TtsEngine(QObject):
    """
    TTS_PROVIDER=edge 시 edge-tts 합성 + Qt 재생, 실패 시 FallbackTTSEngine.

    추후 MeloTTS/XTTS 등은 파일 합성 후 동일 play_mp3 슬롯으로 확장하면 됨.
    """

    def __init__(
        self,
        settings: Settings,
        playback_bridge: EdgeTtsPlaybackBridge | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._fallback = FallbackTTSEngine(settings)
        self._edge = EdgeTTSEngine(settings)
        self._bridge = playback_bridge
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending_on_done: Optional[Callable[[], None]] = None
        self._playback_token = 0

        if self._bridge is not None:
            self._bridge.setParent(self)
            self._bridge.playback_finished.connect(self._on_edge_playback_finished)

    @property
    def playback_gen(self) -> int:
        """재생 슬롯이 기대하는 합성 세대 번호 (브리지가 비교)."""
        return self._playback_token

    def _on_edge_playback_finished(self) -> None:
        self._invoke_done()

    def _invoke_done(self) -> None:
        with self._lock:
            cb = self._pending_on_done
            self._pending_on_done = None
        if cb:
            cb()

    @pyqtSlot()
    def _defer_invoke_done(self) -> None:
        """워커에서 중단·실패 시 메인 스레드로 완료 통지."""
        self._invoke_done()

    def stop(self) -> None:
        self._stop.set()
        self._playback_token += 1  # 진행 중 합성·재생 무효화
        self._fallback.stop()
        if self._bridge:
            self._bridge.stop_playback()

    def speak(
        self,
        text: str,
        on_start: Optional[Callable[[], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """백그라운드에서 합성·재생. UI 스레드를 블로킹하지 않음."""
        self.stop()
        self._stop.clear()
        with self._lock:
            self._pending_on_done = on_done
        self._playback_token += 1
        token = self._playback_token

        def run() -> None:
            if on_start:
                on_start()
            want_edge = self._settings.tts_provider in {"edge", "microsoft", "azure"}
            bridge_ok = self._bridge is not None and self._bridge.is_available()
            if want_edge and bridge_ok:
                fd, tmp = tempfile.mkstemp(suffix=".mp3", prefix="iris_edge_")
                os.close(fd)
                out = Path(tmp)
                try:
                    ok = self._edge.render_to_file_sync(text, out)
                    if self._stop.is_set() or token != self.playback_gen:
                        try:
                            out.unlink(missing_ok=True)
                        except OSError:
                            pass
                        QMetaObject.invokeMethod(
                            self,
                            "_defer_invoke_done",
                            Qt.ConnectionType.QueuedConnection,
                        )
                        return
                    if ok and out.is_file() and out.stat().st_size > 0:
                        self._bridge.play_mp3.emit(token, str(out))
                        return
                except Exception:
                    try:
                        out.unlink(missing_ok=True)
                    except OSError:
                        pass
                if self._stop.is_set() or token != self.playback_gen:
                    QMetaObject.invokeMethod(
                        self,
                        "_defer_invoke_done",
                        Qt.ConnectionType.QueuedConnection,
                    )
                    return
                self._fallback.speak(text, on_start=None, on_done=self._invoke_done)
                return

            if self._stop.is_set() or token != self.playback_gen:
                QMetaObject.invokeMethod(
                    self,
                    "_defer_invoke_done",
                    Qt.ConnectionType.QueuedConnection,
                )
                return
            self._fallback.speak(text, on_start=None, on_done=self._invoke_done)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
