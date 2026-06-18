"""Iris 상태 비주얼라이저 — 구체 코어를 감싼 얇은 래퍼."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QEvent, QObject, Qt
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
        self._orb_anchor: QWidget | None = None
        self._anchor_filter: _OrbAnchorEventFilter | None = None

    def set_orb_anchor(self, widget: QWidget | None) -> None:
        """구체 중심을 레이아웃 여백(orb spacer) 중앙에 맞춘다."""
        if self._orb_anchor is not None and self._anchor_filter is not None:
            self._orb_anchor.removeEventFilter(self._anchor_filter)
        self._orb_anchor = widget
        if widget is not None:
            self._anchor_filter = _OrbAnchorEventFilter(self)
            widget.installEventFilter(self._anchor_filter)
        else:
            self._anchor_filter = None
        self._sync_orb_anchor()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._particle.setGeometry(self.rect())
        self._sync_orb_anchor()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_orb_anchor()

    def _sync_orb_anchor(self) -> None:
        anchor = self._orb_anchor
        if anchor is None or not anchor.isVisible():
            self._particle.clear_custom_center()
            return
        center = anchor.mapTo(self, anchor.rect().center())
        self._particle.set_custom_center(center.x(), center.y())

    def set_state(self, state: AppState) -> None:
        self._particle.set_state(state.name)

    def set_mic_level(self, level: float) -> None:
        self._particle.set_audio_level(level)

    def particle_core(self) -> ParticleVisualizer:
        """TTS/레벨 미터 등에서 직접 ParticleVisualizer에 접근할 때 사용."""
        return self._particle


class _OrbAnchorEventFilter(QObject):
    """앵커 위젯 이동·리사이즈 시 구체 위치 동기화."""

    def __init__(self, visualizer: Visualizer) -> None:
        super().__init__(visualizer)
        self._visualizer = visualizer

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            self._visualizer._sync_orb_anchor()
        return super().eventFilter(watched, event)
