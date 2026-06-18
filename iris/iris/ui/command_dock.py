"""하단 Command Dock — IDE·음성·입력·전송."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.ui.mic_waveform_bar import MicWaveformBar
from iris.ui.theme_tokens import TOKENS


class CommandDock(QWidget):
    """입력·음성·IDE 전환을 하나의 dock으로 정리."""

    send_clicked = pyqtSignal(str)
    ide_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CommandDock")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(96)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(TOKENS.spacing_xs)

        top_row = QHBoxLayout()
        top_row.setSpacing(TOKENS.spacing_sm)

        self._ide_button = QPushButton("IDE")
        self._ide_button.setObjectName("CommandDockIdeButton")
        self._ide_button.setToolTip("Iris IDE 작업공간으로 전환")
        self._ide_button.setFixedHeight(44)
        self._ide_button.setMinimumWidth(52)
        self._ide_button.clicked.connect(self.ide_clicked.emit)
        top_row.addWidget(self._ide_button)

        voice_col = QVBoxLayout()
        voice_col.setSpacing(2)
        self._voice_status = QLabelVoiceStatus()
        self._waveform = MicWaveformBar()
        self._waveform.setMinimumHeight(44)
        voice_col.addWidget(self._voice_status)
        voice_col.addWidget(self._waveform)
        voice_wrap = QWidget()
        voice_wrap.setObjectName("CommandDockVoiceWrap")
        voice_wrap.setLayout(voice_col)
        top_row.addWidget(voice_wrap, 1)

        root.addLayout(top_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(TOKENS.spacing_sm)

        self._input = QLineEdit()
        self._input.setObjectName("CommandDockInput")
        self._input.setPlaceholderText("Message Iris… (Enter to send, Shift+Enter for newline)")
        self._input.setMinimumHeight(46)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._emit_send)
        input_row.addWidget(self._input, 1)

        self._send_button = QPushButton("Send")
        self._send_button.setObjectName("CommandDockSendButton")
        self._send_button.setToolTip("Send message")
        self._send_button.setFixedSize(72, 46)
        self._send_button.setEnabled(False)
        self._send_button.clicked.connect(self._emit_send)
        input_row.addWidget(self._send_button)

        root.addLayout(input_row)

    @property
    def input(self) -> QLineEdit:
        return self._input

    @property
    def waveform(self) -> MicWaveformBar:
        return self._waveform

    @property
    def ide_button(self) -> QPushButton:
        return self._ide_button

    def set_mic_level(self, level: float) -> None:
        self._waveform.set_level(level)

    def set_speech_threshold_rms(self, speech_rms: float) -> None:
        self._waveform.set_threshold_rms(speech_rms)

    def set_voice_state(self, label: str, *, kind: str = "idle") -> None:
        """음성 파이프라인 상태 표시."""
        self._voice_status.set_state(label, kind=kind)

    def set_ide_active(self, active: bool) -> None:
        self._ide_button.setProperty("active", active)
        self._ide_button.style().unpolish(self._ide_button)
        self._ide_button.style().polish(self._ide_button)
        self._ide_button.setText("Back" if active else "IDE")
        self._ide_button.setToolTip(
            "기존 Iris 화면으로 복귀" if active else "Iris IDE 작업공간으로 전환"
        )

    def _on_text_changed(self, text: str) -> None:
        self._send_button.setEnabled(bool(text.strip()))

    def _emit_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.send_clicked.emit(text)


class QLabelVoiceStatus(QWidget):
    """음성 상태 한 줄."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CommandDockVoiceStatus")
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(TOKENS.spacing_xs)
        self._dot = QLabel("●")
        self._label = QLabel("Voice idle")
        self._label.setObjectName("CommandDockVoiceLabel")
        row.addWidget(self._dot)
        row.addWidget(self._label)
        row.addStretch(1)
        self.set_state("Voice idle", kind="idle")

    def set_state(self, text: str, *, kind: str = "idle") -> None:
        colors = {
            "idle": TOKENS.text_muted,
            "listening": TOKENS.neon_cyan,
            "processing": TOKENS.warning,
            "error": TOKENS.error,
        }
        color = colors.get(kind, TOKENS.text_secondary)
        self._dot.setStyleSheet(
            f"color: {color}; font-size: 9px; background: transparent; border: none;"
        )
        self._label.setText(text)
