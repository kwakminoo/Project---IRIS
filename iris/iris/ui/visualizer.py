"""Iris 상태 비주얼라이저 — 파티클 코어를 감싼 얇은 래퍼."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from iris.core.state_machine import AppState
from iris.ui.particle_visualizer import ParticleVisualizer


class Visualizer(QWidget):
    """
    MainWindow가 기대하는 API(set_state(AppState), set_mic_level)를 유지하고
    실제 렌더링은 독립 컴포넌트 ParticleVisualizer에 위임한다.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._particle = ParticleVisualizer(self)
        layout.addWidget(self._particle, 1)

    def set_state(self, state: AppState) -> None:
        self._particle.set_state(state.name)

    def set_mic_level(self, level: float) -> None:
        self._particle.set_audio_level(level)

    def particle_core(self) -> ParticleVisualizer:
        """TTS/레벨 미터 등에서 직접 ParticleVisualizer에 접근할 때 사용."""
        return self._particle
