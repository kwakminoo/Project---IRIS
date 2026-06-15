"""Live Activity / Internal Log — 실제 파이프라인 이벤트 스트림 (English only)."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette, QTextCursor
from PyQt6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget

from iris.core.activity_privacy import prepare_activity_line
from iris.ui.theme_tokens import TOKENS


class UiActivityRelay(QObject):
    """push_activity_line 싱크를 Qt 메인 스레드로 안전하게 넘김."""

    line = pyqtSignal(str)

    def push(self, message: str) -> None:
        safe = prepare_activity_line(message)
        if safe:
            self.line.emit(safe)


_MAX_DOC_LINES = 280
_CHARS_PER_TICK_IDLE = 2
_CHARS_BURST = 8
_TICK_MS = 32


class LiveActivityPanel(QWidget):
    """
    Visualizer(구체)와 채팅 패널 사이 — 채팅과 동일 열 폭으로 내부 로그 표시.
    줄 단위 큐 + 문자 단위 타핑으로 버스트 완충.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LiveActivityPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(72)
        self.setMaximumHeight(90)
        self.setStyleSheet(
            """
            QWidget#LiveActivityPanel {
                background: transparent;
            }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 6)
        lay.setSpacing(4)

        hdr = QLabel("Live Activity / Internal Log")
        hdr.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        hdr.setAutoFillBackground(False)
        hdr.setStyleSheet(
            f"color: {TOKENS.text_hud_label}; font-size: {TOKENS.font_size_hud}; font-weight: 500;"
            " letter-spacing: 1px; background: transparent;"
        )
        lay.addWidget(hdr)

        self._editor = QPlainTextEdit()
        self._editor.setObjectName("LiveActivityLog")
        self._editor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._editor.setAutoFillBackground(False)
        self._editor.setReadOnly(True)
        self._editor.setUndoRedoEnabled(False)
        self._editor.setPlaceholderText("Idle.")
        self._editor.setMaximumBlockCount(_MAX_DOC_LINES)
        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = QFont("Courier New", 10)
        self._editor.setFont(font)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._editor.setFrameShape(QFrame.Shape.NoFrame)
        transparent = QColor(0, 0, 0, 0)
        editor_pal = self._editor.palette()
        editor_pal.setColor(QPalette.ColorRole.Base, transparent)
        editor_pal.setColor(QPalette.ColorRole.Window, transparent)
        self._editor.setPalette(editor_pal)
        self._editor.setStyleSheet(
            """
            QPlainTextEdit#LiveActivityLog {
                background: transparent;
                background-color: transparent;
                color: rgba(226, 232, 240, 0.68);
                border: none;
                outline: none;
                padding: 0 2px 2px 2px;
            }
            QPlainTextEdit#LiveActivityLog QScrollBar:vertical,
            QPlainTextEdit#LiveActivityLog QScrollBar:horizontal {
                width: 0px;
                height: 0px;
                background: transparent;
            }
            """
        )
        lay.addWidget(self._editor, 1)

        self._queue: deque[str] = deque()
        self._current_line: str = ""
        self._cursor_pos = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    def enqueue_typed_line(self, line: str) -> None:
        """메인 스레드에서만 호출 (Relay 시그널 슬롯)."""
        if not line:
            return
        self._queue.append(line)
        if not self._timer.isActive():
            self._timer.start()

    def _on_tick(self) -> None:
        if not self._current_line:
            if not self._queue:
                self._timer.stop()
                return
            self._current_line = self._queue.popleft()
            self._cursor_pos = 0

        burst = _CHARS_BURST if len(self._queue) >= 4 else _CHARS_PER_TICK_IDLE
        end = min(len(self._current_line), self._cursor_pos + burst)
        chunk = self._current_line[self._cursor_pos:end]
        self._cursor_pos = end

        cur = self._editor.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(chunk)
        self._editor.setTextCursor(cur)

        if self._cursor_pos >= len(self._current_line):
            cur = self._editor.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            cur.insertText("\n")
            self._editor.setTextCursor(cur)
            self._current_line = ""
            self._cursor_pos = 0

        sb = self._editor.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_for_idle(self) -> None:
        """Idle 복귀 시 과한 잔상을 줄이고 placeholder에 맡김."""
        self._queue.clear()
        self._current_line = ""
        self._cursor_pos = 0
        self._timer.stop()
        self._editor.clear()
