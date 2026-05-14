"""채팅 패널."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
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
    listen_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Iris에게 메시지를 입력하세요…")
        self._input.returnPressed.connect(self._emit_send)
        btn_send = QPushButton("전송")
        btn_send.clicked.connect(self._emit_send)
        btn_mic = QPushButton("듣기")
        btn_mic.clicked.connect(self.listen_clicked.emit)

        row = QHBoxLayout()
        row.addWidget(self._input, 1)
        row.addWidget(btn_send)
        row.addWidget(btn_mic)

        root = QVBoxLayout(self)
        root.addWidget(self._log, 1)
        root.addLayout(row)

    def append_message(self, who: str, text: str) -> None:
        self._log.append(f"<b>{who}</b>: {text}")

    def _emit_send(self) -> None:
        t = self._input.text().strip()
        if not t:
            return
        self._input.clear()
        self.send_clicked.emit(t)
