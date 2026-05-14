"""Iris 상태 비주얼라이저."""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from iris.core.state_machine import AppState


class Visualizer(QWidget):
    """상태별 애니메이션."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = AppState.IDLE
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)
        self._mic_level = 0.0

    def set_state(self, state: AppState) -> None:
        self._state = state

    def set_mic_level(self, level: float) -> None:
        self._mic_level = max(0.0, min(1.0, level))

    def _tick(self) -> None:
        self._t += 0.05
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        base = QColor("#6d28d9")
        accent = QColor("#38bdf8")

        painter.fillRect(0, 0, w, h, QColor("#0f172a"))

        if self._state is AppState.IDLE:
            r = 40 + 8 * math.sin(self._t)
            painter.setBrush(base)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
        elif self._state is AppState.LISTENING:
            for i in range(5):
                amp = (0.2 + 0.8 * self._mic_level) * 30
                hbar = amp * abs(math.sin(self._t * 3 + i * 0.6))
                x = int(cx - 80 + i * 35)
                y = int(cy - hbar / 2)
                painter.fillRect(x, y, 14, int(hbar), accent)
        elif self._state is AppState.PROCESSING:
            for i in range(3):
                alpha = 0.3 + 0.7 * ((math.sin(self._t * 4 + i) + 1) / 2)
                c = QColor(accent)
                c.setAlphaF(alpha)
                painter.setPen(QPen(c, 6))
                painter.drawArc(int(cx - 60), int(cy - 60), 120, 120, int((i * 120 + self._t * 200) % 5760), 1440)
        elif self._state is AppState.EXECUTING:
            painter.setPen(QPen(accent, 4))
            for i in range(8):
                ang = self._t * 5 + i * math.pi / 4
                r1, r2 = 30, 55
                painter.drawLine(
                    int(cx + r1 * math.cos(ang)),
                    int(cy + r1 * math.sin(ang)),
                    int(cx + r2 * math.cos(ang)),
                    int(cy + r2 * math.sin(ang)),
                )
        elif self._state is AppState.RESPONDING:
            r = 48 + 5 * math.sin(self._t * 2)
            painter.setBrush(accent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
        elif self._state is AppState.MONITORING:
            painter.setPen(QPen(base, 2))
            nodes = [(cx - 80, cy - 20), (cx, cy - 50), (cx + 80, cy - 10), (cx, cy + 40)]
            for a, b in zip(nodes, nodes[1:] + [nodes[0]]):
                painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
            for x, y in nodes:
                painter.setBrush(accent)
                painter.drawEllipse(int(x - 6), int(y - 6), 12, 12)
        elif self._state is AppState.ALERTING:
            flash = (math.sin(self._t * 8) + 1) / 2
            c = QColor("#f97316")
            c.setAlphaF(0.3 + 0.7 * flash)
            painter.setBrush(c)
            painter.drawRect(0, 0, w, h)
        elif self._state is AppState.ERROR:
            painter.setPen(QPen(QColor("#ef4444"), 6))
            painter.drawLine(int(cx - 40), int(cy - 40), int(cx + 40), int(cy + 40))
            painter.drawLine(int(cx - 40), int(cy + 40), int(cx + 40), int(cy - 40))
