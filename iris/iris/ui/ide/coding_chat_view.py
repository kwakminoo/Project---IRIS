"""IDE 코딩 채팅 뷰 — ChatPanel과 동일한 표시 API."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QPushButton,
  QTextEdit,
  QVBoxLayout,
  QWidget,
)

from iris.ui.chat_display import chat_body_to_html, markdown_to_chat_html
from iris.ui.mic_waveform_bar import MicWaveformBar
from iris.ui.theme_tokens import TOKENS


class CodingChatView(QWidget):
  """바이브 코딩용 텍스트·음성 입력 + 대화 기록."""

  send_clicked = pyqtSignal(str)

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("CodingChatView")
    lay = QVBoxLayout(self)
    lay.setContentsMargins(8, 4, 8, 8)
    lay.setSpacing(6)

    self._context_label = QLabel("Workspace: —")
    self._context_label.setWordWrap(True)
    self._context_label.setStyleSheet(
      f"color: {TOKENS.text_secondary}; font-size: 11px;"
    )
    lay.addWidget(self._context_label)

    self._log = QTextEdit()
    self._log.setReadOnly(True)
    self._log.setPlaceholderText("코딩 요청을 입력하세요…")
    lay.addWidget(self._log, 1)

    input_row = QHBoxLayout()
    self._input = QLineEdit()
    self._input.setPlaceholderText("코딩 요청…")
    self._input.returnPressed.connect(self._emit_send)
    input_row.addWidget(self._input, 1)

    self._send_btn = QPushButton("전송")
    self._send_btn.clicked.connect(self._emit_send)
    input_row.addWidget(self._send_btn)
    lay.addLayout(input_row)

    self._wave = MicWaveformBar()
    lay.addWidget(self._wave)

  def _emit_send(self) -> None:
    text = self._input.text().strip()
    if text:
      self.send_clicked.emit(text)
      self._input.clear()

  def set_workspace_context(self, summary: str) -> None:
    self._context_label.setText(summary or "Workspace: —")

  def append_message_instant(self, speaker: str, body: str) -> None:
    html = markdown_to_chat_html(f"**{speaker}:** {body}")
    self._log.append(html)

  def append_message_typed(self, speaker: str, body: str, *, speech_sync: bool = False) -> None:
    # IDE 패널은 즉시 표시 (타이핑 동기는 간소화)
    self.append_message_instant(speaker, body)

  def begin_stream_message(self, speaker: str = "Iris") -> None:
    self._stream_speaker = speaker
    self._stream_body = ""

  def append_stream_chunk(self, chunk: str) -> None:
    if not hasattr(self, "_stream_body"):
      self.begin_stream_message()
    self._stream_body += chunk
    html = chat_body_to_html(f"**{self._stream_speaker}:** {self._stream_body}")
    self._log.moveCursor(self._log.textCursor().MoveOperation.End)
    self._log.insertHtml(html + "<br/>")

  def complete_user_message_typed(self, text: str) -> None:
    self.append_message_instant("나", text)

  def begin_user_listening(self) -> None:
    self._input.setPlaceholderText("듣는 중…")

  def cancel_user_listening(self) -> None:
    self._input.setPlaceholderText("코딩 요청…")

  def set_mic_level(self, level: float) -> None:
    self._wave.set_level(level)

  def on_speech_typing_finished(self, *, flush: bool = True) -> None:
    pass

  def input_text(self) -> str:
    return self._input.text()

  def set_input_text(self, text: str) -> None:
    self._input.setText(text)
