"""Animated Iris core visualizer — 사이버스페이스 입자 네트워크 orb."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QWidget

# 상태별 시각 프로필 — 청색·시안 네온 계열
_STATE_PROFILES: dict[str, dict[str, float | tuple[int, int, int]]] = {
    "IDLE": {
        "pulse": 0.022,
        "glow": 0.38,
        "ring": 0.20,
        "speed": 0.65,
        "accent": (59, 130, 246),
    },
    "LISTENING": {
        "pulse": 0.065,
        "glow": 0.62,
        "ring": 0.44,
        "speed": 1.25,
        "accent": (34, 211, 238),
    },
    "PROCESSING": {
        "pulse": 0.048,
        "glow": 0.74,
        "ring": 0.58,
        "speed": 2.0,
        "accent": (96, 165, 250),
    },
    "EXECUTING": {
        "pulse": 0.080,
        "glow": 0.82,
        "ring": 0.70,
        "speed": 2.5,
        "accent": (56, 189, 248),
    },
    "RESPONDING": {
        "pulse": 0.070,
        "glow": 0.68,
        "ring": 0.48,
        "speed": 1.55,
        "accent": (34, 211, 238),
    },
    "MONITORING": {
        "pulse": 0.035,
        "glow": 0.50,
        "ring": 0.40,
        "speed": 0.95,
        "accent": (129, 140, 248),
    },
    "ALERTING": {
        "pulse": 0.100,
        "glow": 0.90,
        "ring": 0.85,
        "speed": 2.8,
        "accent": (251, 191, 36),
    },
    "ERROR": {
        "pulse": 0.075,
        "glow": 0.76,
        "ring": 0.65,
        "speed": 2.1,
        "accent": (248, 113, 113),
    },
}

_PARTICLE_COUNT = 52
_CONNECT_DIST = 0.38


def _asset_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / relative_path


def _fibonacci_sphere(n: int, seed: int = 42) -> list[tuple[float, float, float]]:
    """구 표면 균등 분포 좌표."""
    rng = random.Random(seed)
    pts: list[tuple[float, float, float]] = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (i / float(max(n - 1, 1))) * 2.0
        r = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        jitter = 0.04 * rng.random()
        pts.append((x + jitter, y + jitter, z + jitter))
    return pts


class ParticleVisualizer(QWidget):
    """중앙 사이버스페이스 orb — 입자 네트워크 + 상태 반응."""

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
        self._core_r = 60.0
        self._custom_center: tuple[float, float] | None = None
        self._size_scale = 1.0
        self._sphere_pts = _fibonacci_sphere(_PARTICLE_COUNT)
        self._core_image = QPixmap(str(_asset_path("visuals/iris_core.png")))

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

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

    def set_custom_center(self, cx: float, cy: float) -> None:
        """레이아웃 앵커 등으로 구체 중심을 고정한다."""
        self._custom_center = (float(cx), float(cy))
        self.update()

    def clear_custom_center(self) -> None:
        self._custom_center = None
        self._recompute_geometry()

    def set_size_scale(self, scale: float) -> None:
        """구체 반경 배율 — IDE 패널 등 컴팩트 영역 확대용."""
        self._size_scale = max(0.25, float(scale))
        self._recompute_geometry()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _recompute_geometry(self) -> None:
        width, height = max(self.width(), 1), max(self.height(), 1)
        if self._custom_center is None:
            self._cx = width * 0.5
            # 로그창 위쪽 중앙에 오도록 기본 Y를 올림
            self._cy = height * 0.36
        else:
            self._cx, self._cy = self._custom_center
        self._core_r = min(width, height) * 0.18 * self._size_scale

    def _profile(self) -> dict[str, float | tuple[int, int, int]]:
        return _STATE_PROFILES.get(self._state_name, _STATE_PROFILES["IDLE"])

    def _tick(self) -> None:
        speed = float(self._profile()["speed"]) * self._activity_level
        self._t += 0.026 * max(0.35, speed)
        self._smooth_audio += (self._audio_level - self._smooth_audio) * 0.14
        self._audio_level *= 0.88
        self._state_burst *= 0.90
        if self._state_burst < 0.01:
            self._state_burst = 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        if self.width() < 4 or self.height() < 4:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx, cy = self._cx, self._cy
        profile = self._profile()
        accent = profile["accent"]
        assert isinstance(accent, tuple)
        synthetic_voice = self._synthetic_voice_level()
        energy = min(1.0, max(self._smooth_audio, synthetic_voice) + self._state_burst * 0.32)

        self._draw_back_glow(painter, cx, cy, accent, energy)
        self._draw_orbit_rings(painter, cx, cy, accent, energy)
        self._draw_state_effects(painter, cx, cy, accent, energy)
        self._draw_core_image(painter, cx, cy, energy)
        self._draw_front_sheen(painter, cx, cy, accent, energy)

        painter.end()

    def _project_sphere(
        self,
        cx: float,
        cy: float,
        radius: float,
        energy: float,
    ) -> list[tuple[float, float, float, float]]:
        """3D 구 좌표 → 2D (x, y, depth, size)."""
        rot_y = self._t * 0.55
        rot_x = self._t * 0.28
        cos_y, sin_y = math.cos(rot_y), math.sin(rot_y)
        cos_x, sin_x = math.cos(rot_x), math.sin(rot_x)
        out: list[tuple[float, float, float, float]] = []
        scale = radius * (1.0 + float(self._profile()["pulse"]) * math.sin(self._t * 1.6))
        for px, py, pz in self._sphere_pts:
            x1 = px * cos_y + pz * sin_y
            z1 = -px * sin_y + pz * cos_y
            y2 = py * cos_x - z1 * sin_x
            z2 = py * sin_x + z1 * cos_x
            depth = (z2 + 1.0) * 0.5
            sx = cx + x1 * scale
            sy = cy + y2 * scale * 0.92
            size = 1.2 + depth * 1.8 + energy * 0.4
            out.append((sx, sy, depth, size))
        return out

    def _draw_particle_network(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> list[tuple[float, float, float, float]]:
        projected = self._project_sphere(cx, cy, self._core_r * 1.05, energy)
        n = len(projected)
        connect_sq = (_CONNECT_DIST * self._core_r) ** 2

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        for i in range(n):
            x1, y1, d1, _ = projected[i]
            for j in range(i + 1, n):
                x2, y2, d2, _ = projected[j]
                dx, dy = x2 - x1, y2 - y1
                if dx * dx + dy * dy > connect_sq:
                    continue
                avg_d = (d1 + d2) * 0.5
                alpha = int((12 + 28 * energy) * avg_d)
                pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
                pen.setWidthF(0.6)
                painter.setPen(pen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        for x, y, depth, size in projected:
            alpha = int(40 + 180 * depth + 60 * energy)
            r = size * (0.9 + energy * 0.25)
            grad = QRadialGradient(x, y, r * 2)
            grad.setColorAt(0.0, QColor(255, 255, 255, min(255, alpha + 40)))
            grad.setColorAt(0.35, QColor(accent[0], accent[1], accent[2], alpha))
            grad.setColorAt(1.0, QColor(accent[0], accent[1], accent[2], 0))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))

        painter.restore()
        return projected

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
        radius = self._core_r * (1.65 + energy * 0.35)
        gradient = QRadialGradient(cx, cy, radius)
        gradient.setColorAt(0.0, QColor(accent[0], accent[1], accent[2], int(65 + glow * 50)))
        gradient.setColorAt(0.35, QColor(37, 99, 235, int(28 + 42 * energy)))
        gradient.setColorAt(0.65, QColor(13, 40, 71, int(12 + 20 * energy)))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), gradient)

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
        for idx, scale in enumerate((0.88, 1.08, 1.28)):
            wobble = 1.0 + math.sin(self._t * (1.0 + idx * 0.22) + idx) * 0.015
            radius = self._core_r * scale * wobble * (1.0 + self._state_burst * 0.10)
            alpha = int((18 + 28 * energy) * ring_strength / (idx + 1))
            pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
            pen.setWidthF(0.7 + energy * 0.5)
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
        for idx, radius_scale in enumerate((1.04, 1.20)):
            radius = self._core_r * radius_scale
            pen = QPen(QColor(accent[0], accent[1], accent[2], int(55 + energy * 75)))
            pen.setWidthF(1.2 + idx * 0.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            start = int((self._t * (130 + idx * 70) + idx * 120) * 16)
            span = int((52 + energy * 38) * 16)
            painter.drawArc(rect, start, span)
            painter.drawArc(rect, start + int(180 * 16), int(span * 0.5))

    def _draw_voice_ripples(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        for idx in range(3):
            phase = (self._t * 0.75 + idx / 3) % 1.0
            radius = self._core_r * (0.78 + phase * 0.58)
            alpha = int((1.0 - phase) * (32 + 70 * energy))
            pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
            pen.setWidthF(0.9 + energy * 1.0)
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
        radius = self._core_r * (0.80 + phase * 0.68)
        alpha = int(self._state_burst * 130)
        pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
        pen.setWidthF(1.8)
        painter.setPen(pen)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

    def _draw_core_image(self, painter: QPainter, cx: float, cy: float, energy: float) -> None:
        if self._core_image.isNull():
            self._draw_procedural_core(painter, cx, cy, energy)
            return

        pulse = float(self._profile()["pulse"])
        breathe = math.sin(self._t * 1.5)
        side = self._core_r * 2.2 * (1.0 + pulse * breathe + energy * 0.03)
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
        inner_side = side * 0.52
        inner_rect = QRectF(cx - inner_side / 2, cy - inner_side / 2, inner_side, inner_side)
        inner_clip = QPainterPath()
        inner_clip.addEllipse(inner_rect)
        rotation = self._t * 2.8

        painter.save()
        painter.setOpacity(0.50 + min(0.22, energy * 0.20))
        painter.setClipPath(outer_clip.subtracted(inner_clip))
        painter.translate(cx, cy)
        painter.rotate(rotation)
        painter.translate(-cx, -cy)
        painter.drawPixmap(rect, self._core_image, source_rect)
        painter.restore()

        painter.save()
        painter.setOpacity(0.95)
        painter.setClipPath(inner_clip)
        painter.drawPixmap(rect, self._core_image, source_rect)
        painter.restore()

    def _draw_procedural_core(self, painter: QPainter, cx: float, cy: float, energy: float) -> None:
        """에셋 없을 때 절차적 코어."""
        r = self._core_r * 0.42 * (1.0 + energy * 0.06)
        grad = QRadialGradient(cx, cy, r)
        profile = self._profile()
        accent = profile["accent"]
        assert isinstance(accent, tuple)
        grad.setColorAt(0.0, QColor(255, 255, 255, int(180 + 40 * energy)))
        grad.setColorAt(0.35, QColor(accent[0], accent[1], accent[2], int(140 + 60 * energy)))
        grad.setColorAt(1.0, QColor(accent[0], accent[1], accent[2], 0))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

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
        radius = self._core_r * (0.55 + energy * 0.06)
        sheen = QRadialGradient(cx - radius * 0.2, cy - radius * 0.26, radius)
        sheen.setColorAt(0.0, QColor(255, 255, 255, int(18 + energy * 28)))
        sheen.setColorAt(0.34, QColor(accent[0], accent[1], accent[2], int(8 + energy * 18)))
        sheen.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), sheen)
        painter.restore()
