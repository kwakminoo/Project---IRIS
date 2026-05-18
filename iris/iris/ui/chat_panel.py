"""채팅 패널."""

from __future__ import annotations

import html

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


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
        self._input = QLineEdit()
        self._input.setPlaceholderText("Iris에게 메시지를 입력하세요…")
        self._input.returnPressed.connect(self._emit_send)
        btn_send = QPushButton("전송")
        btn_send.clicked.connect(self._emit_send)

        row = QHBoxLayout()
        row.addWidget(self._input, 1)
        row.addWidget(btn_send)

        root = QVBoxLayout(self)
        root.addWidget(self._log, 1)
        root.addLayout(row)

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
        safe_who = html.escape(who)
        safe_text = html.escape(text).replace("\n", "<br>")
        self._log.append(f"<b>{safe_who}</b>: {safe_text}")

    def append_message_typed(self, who: str, text: str) -> None:
        """한 글자씩 표시 (사용자·Iris 공용)."""
        self.finish_typing()
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._log.toPlainText().strip():
            cursor.insertBlock()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        self._log.setTextCursor(cursor)
        self._typing_text = text
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

    def _emit_send(self) -> None:
        t = self._input.text().strip()
        if not t:
            return
        self._input.clear()
        self.send_clicked.emit(t)
