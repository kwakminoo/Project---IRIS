"""스레드 간 안전한 UI 시그널 브리지."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class UiBridge(QObject):
    """오디오/ TTS 스레드에서 메인 스레드로 이벤트 전달."""

    barge_in = pyqtSignal()
    tts_finished = pyqtSignal()
