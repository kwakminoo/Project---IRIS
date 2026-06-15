"""사이버스페이스 배경 — 성운·지평선 그리드 페인트."""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget

from iris.ui.theme_tokens import TOKENS


class CyberspaceBackground(QWidget):
    """짙은 우주 배경 + 은은한 성운 + 디지털 지평선."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        self._phase += 0.012
        if self._phase > math.tau:
            self._phase -= math.tau
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        w, h = max(self.width(), 1), max(self.height(), 1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 기본 void
        painter.fillRect(0, 0, w, h, QColor(TOKENS.void_black))

        # 수직 그라디언트 — 깊은 남색
        vert = QLinearGradient(0, 0, 0, h)
        vert.setColorAt(0.0, QColor(TOKENS.space_deep))
        vert.setColorAt(0.55, QColor(TOKENS.space_navy))
        vert.setColorAt(1.0, QColor("#04020a"))
        painter.fillRect(0, 0, w, h, vert)

        # 중앙 성운 — orb 뒤 에너지 필드
        cx, cy = w * 0.52, h * 0.38
        nebula_r = max(w, h) * 0.55
        nebula = QRadialGradient(cx, cy, nebula_r)
        pulse = 0.5 + 0.5 * math.sin(self._phase * 0.7)
        nebula.setColorAt(0.0, QColor(168, 85, 247, int(28 + 10 * pulse)))
        nebula.setColorAt(0.25, QColor(109, 40, 217, int(14 + 6 * pulse)))
        nebula.setColorAt(0.55, QColor(45, 10, 58, int(8 + 4 * pulse)))
        nebula.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, w, h, nebula)

        # 보조 마젠타 성운
        nebula2 = QRadialGradient(w * 0.72, h * 0.28, nebula_r * 0.45)
        nebula2.setColorAt(0.0, QColor(232, 121, 249, int(10 + 5 * pulse)))
        nebula2.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, w, h, nebula2)

        # 디지털 지평선 그리드
        self._draw_horizon_grid(painter, w, h)

        painter.end()

    def _draw_horizon_grid(self, painter: QPainter, w: int, h: int) -> None:
        horizon_y = h * 0.82
        vanish_x = w * 0.5

        # 지평선 글로우 라인
        painter.setPen(QColor(139, 92, 246, 22))
        painter.drawLine(0, int(horizon_y), w, int(horizon_y))

        # 원근 그리드
        rows = 6
        cols = 14
        for row in range(1, rows + 1):
            t = row / (rows + 1)
            y = horizon_y + (h - horizon_y) * t * 0.95
            alpha = int(8 + 18 * (1.0 - t))
            painter.setPen(QColor(56, 189, 248, alpha))
            painter.drawLine(0, int(y), w, int(y))

        for col in range(-cols // 2, cols // 2 + 1):
            painter.setPen(QColor(167, 139, 250, 10))
            top_x = vanish_x + col * (w * 0.04)
            bottom_x = vanish_x + col * (w * 0.22)
            painter.drawLine(int(top_x), int(horizon_y * 0.92), int(bottom_x), h)
