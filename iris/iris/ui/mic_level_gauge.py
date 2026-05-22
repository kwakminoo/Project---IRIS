"""마이크 입력 게이지 + 드래그 감도(인식 임계) 막대."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from iris.audio.mic_level import (
    display_level_to_speech_rms,
    speech_rms_to_display_level,
)

_HANDLE_HIT_PX = 12
_MIN_DISPLAY = 0.02
_MAX_DISPLAY = 0.98


class MicLevelGaugeWidget(QWidget):
    """
    가로 게이지: 채워진 영역은 현재 입력 레벨, 세로 막대는 인식 감도 임계값.
    막대 미만 소리는 continuous_listen에서 무시된다.
    """

    threshold_changed = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._level = 0.0
        self._threshold_display = speech_rms_to_display_level(0.018)
        self._dragging = False

    def set_threshold_rms(self, speech_rms: float) -> None:
        self._threshold_display = speech_rms_to_display_level(speech_rms)
        self.update()

    def threshold_rms(self) -> float:
        return display_level_to_speech_rms(self._threshold_display)

    def set_level(self, level: float) -> None:
        incoming = min(1.0, max(0.0, level))
        # 피크 감쇠 — 짧은 소리도 눈에 보이게
        self._level = max(incoming, self._level * 0.88)
        self.update()

    def _inner_rect(self):
        m = 4
        return self.rect().adjusted(m, 22, -m, -6)

    def _display_to_x(self, display: float, inner) -> int:
        span = max(1, inner.width())
        t = min(_MAX_DISPLAY, max(_MIN_DISPLAY, display))
        return int(inner.left() + t * span)

    def _x_to_display(self, x: int, inner) -> float:
        span = max(1, inner.width())
        rel = (x - inner.left()) / span
        return min(_MAX_DISPLAY, max(_MIN_DISPLAY, rel))

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(QColor("#94a3b8"))
        p.setFont(QFont(self.font().family(), 9))
        p.drawText(4, 14, "입력 레벨")
        p.drawText(self.width() - 120, 14, f"감도 {self.threshold_rms():.3f}")

        inner = self._inner_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#13151a"))
        p.drawRoundedRect(inner, 6, 6)

        thresh_x = self._display_to_x(self._threshold_display, inner)
        # 임계 미만 구간 — 인식 안 됨
        below = QRect(inner)
        below.setRight(thresh_x)
        if below.width() > 0:
            p.setBrush(QColor(20, 25, 35, 120))
            p.drawRoundedRect(below, 4, 4)

        level_w = self._display_to_x(self._level, inner) - inner.left()
        if level_w > 0:
            base_color = (
                QColor("#22d3ee")
                if self._level >= self._threshold_display
                else QColor("#475569")
            )
            gradient = QLinearGradient(inner.left(), 0, inner.right(), 0)
            gradient.setColorAt(
                0.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 0)
            )
            gradient.setColorAt(
                0.1, QColor(base_color.red(), base_color.green(), base_color.blue(), 255)
            )
            gradient.setColorAt(
                0.9, QColor(base_color.red(), base_color.green(), base_color.blue(), 255)
            )
            gradient.setColorAt(
                1.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 0)
            )
            center_y = inner.center().y()
            wave_height = max(2, int(self._level * (inner.height() - 4)))
            wave_rect = QRect(
                inner.left(),
                center_y - (wave_height // 2),
                level_w,
                wave_height,
            )
            p.setBrush(gradient)
            p.drawRoundedRect(wave_rect, 4, 4)

        # 감도 막대
        p.setPen(QPen(QColor("#fbbf24"), 2))
        p.drawLine(thresh_x, inner.top() - 2, thresh_x, inner.bottom() + 2)
        p.setBrush(QColor("#fbbf24"))
        tri_top = inner.top() - 8
        p.drawPolygon(
            [
                QPoint(thresh_x - 5, tri_top),
                QPoint(thresh_x + 5, tri_top),
                QPoint(thresh_x, inner.top() - 1),
            ]
        )
        p.end()

    def _near_threshold(self, x: int) -> bool:
        inner = self._inner_rect()
        return abs(x - self._display_to_x(self._threshold_display, inner)) <= _HANDLE_HIT_PX

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._near_threshold(int(event.position().x())):
            self._dragging = True
            self._apply_threshold_x(int(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._apply_threshold_x(int(event.position().x()))
            event.accept()
            return
        if self._near_threshold(int(event.position().x())):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_threshold_x(self, x: int) -> None:
        inner = self._inner_rect()
        self._threshold_display = self._x_to_display(x, inner)
        self.threshold_changed.emit(self.threshold_rms())
        self.update()
