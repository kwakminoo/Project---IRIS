"""Iris 상태 비주얼라이저 — 구체 코어를 감싼 얇은 래퍼."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from iris.core.state_machine import AppState
from iris.ui.particle_visualizer import ParticleVisualizer


class Visualizer(QWidget):
    """
    MainWindow가 기대하는 API(set_state(AppState), set_mic_level)를 유지하고
    실제 렌더링은 구체 코어 컴포넌트에 위임한다.
    창 전체 오버레이 레이어로 쓰일 때 geometry로 꽉 채운다.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._particle = ParticleVisualizer(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._particle.setGeometry(self.rect())

    def set_state(self, state: AppState) -> None:
        self._particle.set_state(state.name)

    def set_mic_level(self, level: float) -> None:
        self._particle.set_audio_level(level)

    def particle_core(self) -> ParticleVisualizer:
        """TTS/레벨 미터 등에서 직접 ParticleVisualizer에 접근할 때 사용."""
        return self._particle
