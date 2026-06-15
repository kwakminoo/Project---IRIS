"""시스템 CPU·GPU·메모리 표시 패널."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from iris.system.metrics_snapshot import MetricsSnapshot
from iris.ui.theme_tokens import TOKENS


class SystemMetricsPanel(QWidget):
  """실시간 시스템 리소스 표시."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("SystemMetricsPanel")
    lay = QVBoxLayout(self)
    lay.setContentsMargins(6, 4, 6, 4)
    lay.setSpacing(6)

    self._cpu_label = QLabel("CPU")
    self._cpu_bar = self._make_bar()
    self._gpu_label = QLabel("GPU")
    self._gpu_bar = self._make_bar()
    self._mem_label = QLabel("MEMORY")
    self._mem_bar = self._make_bar()

    for label, bar in (
      (self._cpu_label, self._cpu_bar),
      (self._gpu_label, self._gpu_bar),
      (self._mem_label, self._mem_bar),
    ):
      lay.addWidget(label)
      lay.addWidget(bar)

  def _make_bar(self) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(True)
    bar.setStyleSheet(
      f"""
      QProgressBar {{
        background: {TOKENS.panel_background};
        border: 1px solid {TOKENS.border_color};
        border-radius: 4px;
        height: 14px;
        color: {TOKENS.text_primary};
      }}
      QProgressBar::chunk {{
        background: {TOKENS.accent_primary};
        border-radius: 3px;
      }}
      """
    )
    return bar

  def apply_snapshot(self, snap: MetricsSnapshot) -> None:
    self._cpu_bar.setValue(int(round(snap.cpu_percent)))
    self._cpu_bar.setFormat(f"{snap.cpu_percent:.0f}%")
    self._mem_bar.setValue(int(round(snap.memory_percent)))
    self._mem_bar.setFormat(f"{snap.memory_percent:.0f}%")
    if snap.gpu_percent is None:
      self._gpu_bar.setValue(0)
      self._gpu_bar.setFormat("N/A")
      self._gpu_label.setText(snap.gpu_label)
    else:
      self._gpu_bar.setValue(int(round(snap.gpu_percent)))
      self._gpu_bar.setFormat(f"{snap.gpu_percent:.0f}%")
      self._gpu_label.setText("GPU")
