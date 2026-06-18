"""모델·상태·TTS 한 줄 표시 — Assistant/IDE 워크스페이스 간 재배치."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusStrip(QWidget):
  """기본 화면·IDE 코딩 패널 상단에 동일하게 쓰는 상태 행."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("StatusStrip")
    row = QHBoxLayout(self)
    row.setContentsMargins(4, 6, 4, 6)
    row.setSpacing(8)

    self.model_label = QLabel()
    self.model_label.setObjectName("ModelStatus")
    row.addWidget(self.model_label)

    self.status_label = QLabel("상태: IDLE")
    self.status_label.setObjectName("StatusPill")
    row.addWidget(self.status_label)

    self.tts_status_label = QLabel()
    self.tts_status_label.setObjectName("TtsStatus")
    row.addWidget(self.tts_status_label)

    row.addStretch(1)
