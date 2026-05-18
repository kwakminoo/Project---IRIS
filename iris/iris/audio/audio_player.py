"""WAV/MP3 오디오 재생 (PyQt6 QtMultimedia)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal, pyqtSlot

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

    _QT_MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover
    QMediaPlayer = None  # type: ignore[misc, assignment]
    QAudioOutput = None  # type: ignore[misc, assignment]
    _QT_MULTIMEDIA_AVAILABLE = False


class AudioPlayer(QObject):
    """
    워커 스레드에서 play_file.emit(gen, path) → 메인 스레드에서 재생.

    gen은 TTSManager.playback_gen과 일치할 때만 재생(이전 합성 결과 무시).
    barge-in 시 stop()으로 즉시 중지.
    """

    playback_finished = pyqtSignal()
    play_file = pyqtSignal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player: Optional[QMediaPlayer] = None
        self._audio: Optional[QAudioOutput] = None
        self._temp_path: Optional[str] = None
        self._end_notified = False
        self._playing = False

        self.play_file.connect(self._on_play_file, Qt.ConnectionType.QueuedConnection)

        if _QT_MULTIMEDIA_AVAILABLE:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.mediaStatusChanged.connect(self._on_media_status)
            self._player.errorOccurred.connect(self._on_player_error)

    def is_available(self) -> bool:
        return bool(self._player and self._audio)

    def is_playing(self) -> bool:
        return self._playing

    @pyqtSlot(int, str)
    def _on_play_file(self, expected_gen: int, path: str) -> None:
        owner = self.parent()
        if owner is None or getattr(owner, "playback_gen", None) != expected_gen:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
            return
        if not self._player:
            self._notify_done_once()
            return
        self._end_notified = False
        self._temp_path = path
        self._playing = True
        url = QUrl.fromLocalFile(str(Path(path).resolve()))
        self._player.setSource(url)
        self._player.play()

    def _on_media_status(self, status: "QMediaPlayer.MediaStatus") -> None:  # type: ignore[name-defined]
        from PyQt6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._notify_done_once()

    def _on_player_error(self, *_args: object) -> None:
        self._notify_done_once()

    def stop(self) -> None:
        """재생 중지 + 임시 파일 정리."""
        if self._player:
            self._player.stop()
        self._playing = False
        self._cleanup_temp()
        self._notify_done_once()

    def _cleanup_temp(self) -> None:
        p = self._temp_path
        self._temp_path = None
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass

    def _notify_done_once(self) -> None:
        if self._end_notified:
            return
        self._end_notified = True
        self._playing = False
        self._cleanup_temp()
        self.playback_finished.emit()
