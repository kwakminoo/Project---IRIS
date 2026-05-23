"""채팅 패널."""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.ui.chat_display import normalize_chat_body
from iris.ui.mic_waveform_bar import MicWaveformBar


class _ChatInputBar(QWidget):
    """입력칸 + 우측 인라인 전송 버튼."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        super().__init__(parent)
        self.setObjectName("ChatInputBar")
        self.setStyleSheet(
            """
            QWidget#ChatInputBar {
                background-color: #111827;
                border: none;
            }
            QWidget#ChatInputBar QLineEdit {
                background: transparent;
                border: none;
                padding: 8px 4px 8px 12px;
            }
            """
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 6, 4)
        row.setSpacing(4)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Iris에게 메시지를 입력하세요…")
        # 입력창 자체 테두리·배경 — 다크 모드에 맞춘 독립 스타일
        self.input.setStyleSheet(
            """
            QLineEdit {
                background-color: #1a1c24;
                color: #ffffff;
                border: 1px solid #3f3f5f;
                border-radius: 6px;
                padding: 6px 10px;
            }
            """
        )

        self.send_button = QPushButton("↑")
        self.send_button.setObjectName("ChatSendButton")
        self.send_button.setToolTip("전송")
        self.send_button.setFixedSize(32, 32)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setEnabled(False)
        self.send_button.setStyleSheet(
            """
            QPushButton#ChatSendButton {
                background-color: #4f46e5;
                color: #ffffff;
                border: none;
                border-radius: 16px;
                font-size: 15px;
                font-weight: 700;
                padding: 0;
            }
            QPushButton#ChatSendButton:hover:enabled {
                background-color: #6366f1;
            }
            QPushButton#ChatSendButton:pressed:enabled {
                background-color: #4338ca;
            }
            QPushButton#ChatSendButton:disabled {
                background-color: #1e293b;
                color: #475569;
            }
            """
        )

        row.addWidget(self.input, 1)
        row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignVCenter)


class _ChatInputArea(QWidget):
    """입력칸 + 하단 마이크 주파수 바."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatInputArea")
        self.setStyleSheet(
            """
            QWidget#ChatInputArea {
                background-color: #0f172a;
                border: 1px solid #3b82f6;
                border-radius: 10px;
            }
            """
        )
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self.input_bar = _ChatInputBar()
        self.waveform = MicWaveformBar()
        self.waveform.setStyleSheet(
            """
            MicWaveformBar {
                background-color: #0b1220;
                border-top: 1px solid #1e3a5f;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }
            """
        )

        col.addWidget(self.input_bar)
        col.addWidget(self.waveform)


class ChatPanel(QWidget):
    send_clicked = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(18)
        self._typing_timer.timeout.connect(self._type_next_chunk)
        self._typing_text = ""
        self._typing_index = 0
        self._user_listening_active = False
        self._input_area = _ChatInputArea()
        self._input = self._input_area.input_bar.input
        self._waveform = self._input_area.waveform
        self._input.returnPressed.connect(self._emit_send)
        self._input.textChanged.connect(self._on_input_changed)
        self._input_area.input_bar.send_button.clicked.connect(self._emit_send)

        root = QVBoxLayout(self)
        root.addWidget(self._log, 1)
        root.addWidget(self._input_area)

    def set_mic_level(self, level: float) -> None:
        """상시 듣기 마이크 레벨 — 하단 주파수 바에 반영."""
        self._waveform.set_level(level)

    def set_speech_threshold_rms(self, speech_rms: float) -> None:
        """인식 감도 임계 — 점선 위치 갱신."""
        self._waveform.set_threshold_rms(speech_rms)

    def begin_user_listening(self) -> None:
        """발화 시작 — 플레이스홀더로 즉시 피드백."""
        self.finish_typing()
        self._remove_user_listening_line()
        self._log.append("<b>나</b>: <i style='color:#94a3b8'>…</i>")
        self._user_listening_active = True

    def set_user_listening_status(self, status: str) -> None:
        """STT 진행 등 상태 문구 갱신."""
        if not self._user_listening_active:
            self.begin_user_listening()
        self._remove_user_listening_line()
        safe = html.escape(status)
        self._log.append(f"<b>나</b>: <i style='color:#94a3b8'>{safe}</i>")
        self._user_listening_active = True

    def cancel_user_listening(self) -> None:
        """인식 취소·게이트 거부 시 플레이스홀더 제거."""
        if self._user_listening_active:
            self._remove_user_listening_line()
        self._user_listening_active = False

    def complete_user_message_typed(self, text: str) -> None:
        """음성 인식 완료 — 플레이스홀더 제거 후 타이핑 효과로 본문 표시."""
        self.cancel_user_listening()
        self.append_message_typed("나", text)

    def append_message(self, who: str, text: str) -> None:
        self.finish_typing()
        body = normalize_chat_body(who, text)
        safe_who = html.escape(who)
        safe_text = html.escape(body).replace("\n", "<br>")
        self._log.append(f"<b>{safe_who}</b>: {safe_text}")

    def append_message_typed(self, who: str, text: str) -> None:
        """한 글자씩 표시 (사용자·Iris 공용)."""
        self.finish_typing()
        body = normalize_chat_body(who, text)
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._log.toPlainText().strip():
            cursor.insertBlock()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        self._log.setTextCursor(cursor)
        self._typing_text = body
        self._typing_index = 0
        self._typing_timer.start()

    def finish_typing(self) -> None:
        """진행 중인 타이핑 효과를 즉시 완료한다."""
        if not self._typing_timer.isActive():
            return
        self._typing_timer.stop()
        remaining = self._typing_text[self._typing_index :]
        if remaining:
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(remaining)
            self._log.setTextCursor(cursor)
        self._typing_text = ""
        self._typing_index = 0

    def _remove_user_listening_line(self) -> None:
        """마지막 '나: …' 플레이스홀더 블록 제거."""
        plain = self._log.toPlainText()
        if not plain.strip():
            return
        lines = plain.split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].startswith("나:"):
            lines.pop()
        self._log.setPlainText("\n".join(lines))
        if lines:
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._log.setTextCursor(cursor)

    def _type_next_chunk(self) -> None:
        if self._typing_index >= len(self._typing_text):
            self._typing_timer.stop()
            self._typing_text = ""
            self._typing_index = 0
            return
        chunk = self._typing_text[self._typing_index : self._typing_index + 2]
        self._typing_index += len(chunk)
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def _on_input_changed(self, text: str) -> None:
        self._input_area.input_bar.send_button.setEnabled(bool(text.strip()))

    def _emit_send(self) -> None:
        t = self._input.text().strip()
        if not t:
            return
        self._input.clear()
        self.send_clicked.emit(t)
