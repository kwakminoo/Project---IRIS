"""IDE용 Iris 구체 위젯 — ParticleVisualizer 재사용."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from iris.core.state_machine import AppState
from iris.ui.particle_visualizer import ParticleVisualizer


class IrisOrbWidget(QWidget):
  """컴팩트 Iris 구체 + 상태 라벨."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IrisOrbWidget")
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    self._particle = ParticleVisualizer(self)
    self._particle.setMinimumHeight(100)
    self._particle.setMaximumHeight(140)
    lay.addWidget(self._particle)

  def set_state(self, state: AppState) -> None:
    self._particle.set_state(state.name)

  def set_mic_level(self, level: float) -> None:
    self._particle.set_audio_level(level)

  def particle_core(self) -> ParticleVisualizer:
    return self._particle

  def setVisible(self, visible: bool) -> None:  # noqa: N802
    super().setVisible(visible)
    if visible:
      self._particle.start()
    else:
      self._particle.stop()
