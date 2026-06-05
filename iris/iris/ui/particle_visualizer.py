"""Animated Iris core visualizer."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QWidget


_STATE_PROFILES: dict[str, dict[str, float | tuple[int, int, int]]] = {
    "IDLE": {
        "pulse": 0.025,
        "glow": 0.34,
        "ring": 0.22,
        "speed": 0.75,
        "accent": (56, 189, 248),
    },
    "LISTENING": {
        "pulse": 0.070,
        "glow": 0.58,
        "ring": 0.42,
        "speed": 1.35,
        "accent": (34, 211, 238),
    },
    "PROCESSING": {
        "pulse": 0.050,
        "glow": 0.70,
        "ring": 0.62,
        "speed": 2.15,
        "accent": (129, 140, 248),
    },
    "EXECUTING": {
        "pulse": 0.085,
        "glow": 0.80,
        "ring": 0.72,
        "speed": 2.65,
        "accent": (96, 165, 250),
    },
    "RESPONDING": {
        "pulse": 0.075,
        "glow": 0.66,
        "ring": 0.50,
        "speed": 1.65,
        "accent": (125, 211, 252),
    },
    "MONITORING": {
        "pulse": 0.040,
        "glow": 0.54,
        "ring": 0.46,
        "speed": 1.05,
        "accent": (45, 212, 191),
    },
    "ALERTING": {
        "pulse": 0.110,
        "glow": 0.95,
        "ring": 0.88,
        "speed": 3.05,
        "accent": (251, 191, 36),
    },
    "ERROR": {
        "pulse": 0.080,
        "glow": 0.72,
        "ring": 0.68,
        "speed": 2.20,
        "accent": (168, 85, 247),
    },
}


def _asset_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / relative_path


class ParticleVisualizer(QWidget):
    """Central animated orb that reacts to Iris state changes."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state_name = "IDLE"
        self._t = 0.0
        self._audio_level = 0.0
        self._smooth_audio = 0.0
        self._activity_level = 1.0
        self._state_burst = 0.0
        self._cx = 0.0
        self._cy = 0.0
        self._core_r = 120.0
        self._core_image = QPixmap(str(_asset_path("visuals/iris_core.png")))

        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute_geometry()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.stop()

    def set_state(self, state: str) -> None:
        name = str(state).strip().upper()
        if name not in _STATE_PROFILES:
            name = "IDLE"
        if name != self._state_name:
            self._state_name = name
            self._state_burst = 1.0
        self.update()

    def set_audio_level(self, level: float) -> None:
        self._audio_level = max(0.0, min(1.0, float(level)))

    def set_activity_level(self, level: float) -> None:
        self._activity_level = max(0.0, min(2.0, float(level)))

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _recompute_geometry(self) -> None:
        width, height = max(self.width(), 1), max(self.height(), 1)
        self._cx = width * 0.5
        self._cy = height * 0.5
        self._core_r = min(width, height) * 0.38

    def _profile(self) -> dict[str, float | tuple[int, int, int]]:
        return _STATE_PROFILES.get(self._state_name, _STATE_PROFILES["IDLE"])

    def _tick(self) -> None:
        speed = float(self._profile()["speed"]) * self._activity_level
        self._t += 0.028 * max(0.35, speed)
        self._smooth_audio += (self._audio_level - self._smooth_audio) * 0.16
        self._audio_level *= 0.90
        self._state_burst *= 0.91
        if self._state_burst < 0.01:
            self._state_burst = 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        if self.width() < 4 or self.height() < 4:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.fillRect(0, 0, self.width(), self.height(), QColor(11, 18, 32, 36))

        cx, cy = self._cx, self._cy
        profile = self._profile()
        accent = profile["accent"]
        assert isinstance(accent, tuple)
        synthetic_voice = self._synthetic_voice_level()
        energy = min(1.0, max(self._smooth_audio, synthetic_voice) + self._state_burst * 0.35)

        self._draw_back_glow(painter, cx, cy, accent, energy)
        self._draw_core_image(painter, cx, cy, energy)

        painter.end()

    def _synthetic_voice_level(self) -> float:
        if self._state_name == "LISTENING":
            return 0.22 + 0.16 * (0.5 + 0.5 * math.sin(self._t * 4.0))
        if self._state_name == "PROCESSING":
            return 0.18 + 0.12 * (0.5 + 0.5 * math.sin(self._t * 7.5))
        if self._state_name == "EXECUTING":
            return 0.30 + 0.18 * (0.5 + 0.5 * math.sin(self._t * 6.2))
        if self._state_name == "RESPONDING":
            return 0.26 + 0.22 * (0.5 + 0.5 * math.sin(self._t * 8.0))
        if self._state_name == "ALERTING":
            return 0.50 + 0.25 * (0.5 + 0.5 * math.sin(self._t * 10.0))
        return 0.0

    def _draw_back_glow(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        glow = float(self._profile()["glow"])
        radius = self._core_r * (1.55 + energy * 0.28)
        gradient = QRadialGradient(cx, cy, radius)
        gradient.setColorAt(0.0, QColor(accent[0], accent[1], accent[2], int(52 + glow * 42)))
        gradient.setColorAt(0.45, QColor(34, 211, 238, int(16 + 38 * energy)))
        gradient.setColorAt(1.0, QColor(8, 47, 73, 0))
        painter.fillRect(
            QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
            gradient,
        )

    def _draw_orbit_rings(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        ring_strength = float(self._profile()["ring"])
        for idx, scale in enumerate((0.82, 1.02, 1.22)):
            wobble = 1.0 + math.sin(self._t * (1.1 + idx * 0.25) + idx) * 0.018
            radius = self._core_r * scale * wobble * (1.0 + self._state_burst * 0.12)
            alpha = int((26 + 34 * energy) * ring_strength / (idx + 1))
            pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
            pen.setWidthF(1.0 + energy * 1.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        painter.restore()

    def _draw_state_effects(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        if self._state_name in {"PROCESSING", "EXECUTING", "ALERTING"}:
            self._draw_rotating_arcs(painter, cx, cy, accent, energy)
        if self._state_name in {"LISTENING", "RESPONDING"}:
            self._draw_voice_ripples(painter, cx, cy, accent, energy)
        if self._state_burst > 0.02:
            self._draw_state_burst(painter, cx, cy, accent)

        painter.restore()

    def _draw_rotating_arcs(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        for idx, radius_scale in enumerate((1.02, 1.18)):
            radius = self._core_r * radius_scale
            pen = QPen(QColor(accent[0], accent[1], accent[2], int(70 + energy * 90)))
            pen.setWidthF(1.7 + idx * 0.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            start = int((self._t * (140 + idx * 80) + idx * 130) * 16)
            span = int((58 + energy * 42) * 16)
            painter.drawArc(rect, start, span)
            painter.drawArc(rect, start + int(180 * 16), int(span * 0.52))

    def _draw_voice_ripples(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        for idx in range(3):
            phase = (self._t * 0.8 + idx / 3) % 1.0
            radius = self._core_r * (0.76 + phase * 0.62)
            alpha = int((1.0 - phase) * (38 + 80 * energy))
            pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
            pen.setWidthF(1.1 + energy * 1.4)
            painter.setPen(pen)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

    def _draw_state_burst(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
    ) -> None:
        phase = 1.0 - self._state_burst
        radius = self._core_r * (0.78 + phase * 0.72)
        alpha = int(self._state_burst * 150)
        pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
        pen.setWidthF(2.4)
        painter.setPen(pen)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

    def _draw_core_image(self, painter: QPainter, cx: float, cy: float, energy: float) -> None:
        if self._core_image.isNull():
            return

        pulse = float(self._profile()["pulse"])
        breathe = math.sin(self._t * 1.7)
        side = self._core_r * 2.42 * (1.0 + pulse * breathe + energy * 0.035)
        rect = QRectF(cx - side / 2, cy - side / 2, side, side)

        source_side = min(self._core_image.width(), self._core_image.height()) * 0.92
        source_rect = QRectF(
            (self._core_image.width() - source_side) / 2,
            (self._core_image.height() - source_side) / 2 - source_side * 0.015,
            source_side,
            source_side,
        )

        outer_clip = QPainterPath()
        outer_clip.addEllipse(rect)
        inner_side = side * 0.56
        inner_rect = QRectF(cx - inner_side / 2, cy - inner_side / 2, inner_side, inner_side)
        inner_clip = QPainterPath()
        inner_clip.addEllipse(inner_rect)

        rotation = self._t * 3.4

        painter.save()
        painter.setOpacity(0.58 + min(0.18, energy * 0.18))
        painter.setClipPath(outer_clip.subtracted(inner_clip))
        painter.translate(cx, cy)
        painter.rotate(rotation)
        painter.translate(-cx, -cy)
        painter.drawPixmap(rect, self._core_image, source_rect)
        painter.restore()

        painter.save()
        painter.setOpacity(0.98)
        painter.setClipPath(inner_clip)
        painter.drawPixmap(rect, self._core_image, source_rect)
        painter.restore()

    def _draw_outer_rotation_highlight(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        radius = self._core_r * 1.08
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        for idx in range(2):
            pen = QPen(QColor(accent[0], accent[1], accent[2], int(28 + energy * 46)))
            pen.setWidthF(1.1 + idx * 0.35)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            direction = 1 if idx == 0 else -1
            start = int((self._t * direction * (18 + idx * 8) + idx * 180) * 16)
            span = int((34 + energy * 20) * 16)
            painter.drawArc(rect, start, span)
        painter.restore()

    def _draw_front_sheen(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        radius = self._core_r * (0.58 + energy * 0.08)
        sheen = QRadialGradient(cx - radius * 0.22, cy - radius * 0.28, radius)
        sheen.setColorAt(0.0, QColor(255, 255, 255, int(22 + energy * 34)))
        sheen.setColorAt(0.34, QColor(accent[0], accent[1], accent[2], int(10 + energy * 22)))
        sheen.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), sheen)
        painter.restore()
