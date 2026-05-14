"""Jarvis 스타일 푸른 파티클 코어 비주얼라이저 (QPainter 전용, 독립 컴포넌트)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget


@dataclass
class Particle:
    """단일 입자 속성."""

    base_angle: float
    radius_norm: float  # 0~1, resize 시 _core_r와 곱해 사용
    speed: float
    size: float
    brightness: float
    phase: float
    layer: int


# 상태별 목표 파라미터 (요구사항 예시와 동일 계열)
_STATE_PROFILES: dict[str, dict[str, float]] = {
    "IDLE": {"count": 180, "speed": 0.3, "pulse": 0.15, "brightness": 0.45},
    "LISTENING": {"count": 220, "speed": 0.6, "pulse": 0.35, "brightness": 0.65},
    "PROCESSING": {"count": 280, "speed": 1.2, "pulse": 0.25, "brightness": 0.8},
    "EXECUTING": {"count": 300, "speed": 1.6, "pulse": 0.3, "brightness": 0.85},
    "RESPONDING": {"count": 240, "speed": 0.8, "pulse": 0.55, "brightness": 0.75},
    "MONITORING": {"count": 260, "speed": 0.7, "pulse": 0.25, "brightness": 0.7},
    "ALERTING": {"count": 320, "speed": 1.8, "pulse": 0.8, "brightness": 1.0},
    "ERROR": {"count": 220, "speed": 0.9, "pulse": 0.45, "brightness": 0.65},
}


class ParticleVisualizer(QWidget):
    """
    푸른/시안 계열 홀로그래픽 파티클 코어.
    QML/OpenGL 교체를 위해 QWidget 단일 파일로 분리.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state_name = "IDLE"
        self._t = 0.0
        self._audio_level = 0.0
        self._activity_level = 1.0
        self._particles: list[Particle] = []
        self._cx = 0.0
        self._cy = 0.0
        self._core_r = 120.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute_geometry()
        self._ensure_particles()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.stop()

    def _recompute_geometry(self) -> None:
        w, h = max(self.width(), 1), max(self.height(), 1)
        self._cx = w * 0.5
        self._cy = h * 0.5
        # 반응형 코어 반경: 패널이 작아져도 비율 유지
        self._core_r = min(w, h) * 0.38

    def _profile(self) -> dict[str, float]:
        return _STATE_PROFILES.get(self._state_name, _STATE_PROFILES["IDLE"])

    def _ensure_particles(self) -> None:
        target = int(self._profile()["count"])
        if len(self._particles) == target and self._particles:
            return
        rng = random.Random(42)
        self._particles = []
        for i in range(target):
            u = rng.random()
            # 중심에 밀집, 외곽으로 갈수록 드묾
            r_norm = 0.06 + 0.94 * (u**0.42)
            self._particles.append(
                Particle(
                    base_angle=rng.uniform(0.0, math.tau),
                    radius_norm=r_norm,
                    speed=rng.uniform(0.85, 1.15),
                    size=rng.uniform(1.1, 3.2),
                    brightness=rng.uniform(0.55, 1.0),
                    phase=rng.uniform(0.0, math.tau),
                    layer=int(rng.randint(0, 2)),
                )
            )

    def set_state(self, state: str) -> None:
        """상태 문자열 (예: IDLE, LISTENING). 대소문자 무시."""
        name = str(state).strip().upper()
        if name not in _STATE_PROFILES:
            name = "IDLE"
        if name != self._state_name:
            self._state_name = name
            self._ensure_particles()
        self.update()

    def set_audio_level(self, level: float) -> None:
        """0~1, LISTENING/RESPONDING 등 오디오 반응용."""
        self._audio_level = max(0.0, min(1.0, float(level)))

    def set_activity_level(self, level: float) -> None:
        """추가 활동 강도 (모니터링·백그라운드 작업 등 확장용)."""
        self._activity_level = max(0.0, min(2.0, float(level)))

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start(25)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._t += 0.032
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        if self.width() < 4 or self.height() < 4:
            return
        if not self._particles:
            self._recompute_geometry()
            self._ensure_particles()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(11, 18, 32, 40))

        prof = self._profile()
        pulse = prof["pulse"]
        spd = prof["speed"] * self._activity_level
        base_bright = prof["brightness"]

        cx, cy = self._cx, self._cy
        mic = self._audio_level
        if self._state_name == "LISTENING" and mic < 0.02:
            mic = 0.35 + 0.35 * math.sin(self._t * 2.8)

        # 중심부 다층 번짐 (깊이)
        for ring_i, alpha_mul in enumerate((0.12, 0.08, 0.05)):
            gr = QRadialGradient(cx, cy, self._core_r * (0.35 + ring_i * 0.22))
            gr.setColorAt(0.0, QColor(56, 189, 248, int(90 * alpha_mul * 255)))
            gr.setColorAt(0.45, QColor(14, 165, 233, int(50 * alpha_mul * 255)))
            gr.setColorAt(1.0, QColor(8, 47, 73, 0))
            painter.fillRect(0, 0, w, h, gr)

        # 궤도 링 (EXECUTING 등)
        if self._state_name in ("EXECUTING", "MONITORING", "ALERTING"):
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            ring_pen = QPen(QColor(125, 211, 252, 60))
            ring_pen.setWidthF(1.2)
            painter.setPen(ring_pen)
            rr = self._core_r * (1.05 + 0.04 * math.sin(self._t * (1.2 if self._state_name != "ALERTING" else 3.0)))
            painter.drawEllipse(QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr))
            if self._state_name == "EXECUTING":
                r2 = rr * 1.12
                painter.drawEllipse(QRectF(cx - r2, cy - r2, 2 * r2, 2 * r2))

        # MONITORING: 노드 연결 느낌 (일부 입자만)
        if self._state_name == "MONITORING" and len(self._particles) > 8:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(34, 211, 238, 35))
            pen.setWidthF(0.8)
            painter.setPen(pen)
            step = max(len(self._particles) // 14, 1)
            for i in range(0, len(self._particles) - step, step):
                a = self._particles[i]
                b = self._particles[i + step]
                aox, aoy = self._compute_offsets(a, spd, pulse, mic, base_bright)
                box, boy = self._compute_offsets(b, spd, pulse, mic, base_bright)
                painter.drawLine(QPointF(cx + aox, cy + aoy), QPointF(cx + box, cy + boy))

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        glitch = 0.0
        if self._state_name == "ERROR":
            glitch = 0.5 + 0.5 * math.sin(self._t * 11.3)

        for idx, p in enumerate(self._particles):
            ox, oy = self._compute_offsets(p, spd, pulse, mic, base_bright)

            if self._state_name == "ERROR" and (math.sin(self._t * 7 + p.phase) > 0.92):
                ox += 6 * math.sin(self._t * 20 + p.phase)
                oy += 6 * math.cos(self._t * 17 + p.phase)

            px, py = cx + ox, cy + oy

            bright = base_bright * p.brightness
            if self._state_name == "ALERTING":
                bright *= 0.75 + 0.35 * abs(math.sin(self._t * 6 + p.phase))
            if self._state_name == "ERROR":
                bright *= 0.7 + 0.25 * glitch

            r_col, g_col, b_col = self._particle_color(p, bright, idx)

            # 글로우: 바깥 흐릿 + 안쪽 선명
            glow_r = p.size * 2.8
            grad = QRadialGradient(px, py, glow_r)
            grad.setColorAt(0.0, QColor(r_col, g_col, b_col, int(min(255, 220 * bright))))
            grad.setColorAt(0.35, QColor(r_col, g_col, b_col, int(90 * bright)))
            grad.setColorAt(1.0, QColor(r_col, g_col, b_col, 0))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(px - glow_r, py - glow_r, 2 * glow_r, 2 * glow_r))

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _particle_color(self, p: Particle, bright: float, idx: int) -> tuple[int, int, int]:
        """blue/cyan 기반, ALERTING은 약한 amber 포인트, ERROR는 약한 violet/red."""
        t = self._t
        if self._state_name == "ALERTING" and idx % 47 == 0:
            return (251, 191, 36) if bright > 0.45 else (34, 211, 238)
        if self._state_name == "ERROR":
            mix = 0.15 + 0.1 * math.sin(t * 9 + p.phase)
            r = int(96 + 80 * mix)
            g = int(165 - 40 * mix)
            b = int(250 - 30 * mix)
            return (r, g, b)
        # 시안~일렉트릭 블루
        hue_shift = 0.15 * math.sin(t * 0.7 + p.layer)
        r = int(30 + 40 * bright + 20 * hue_shift)
        g = int(180 + 50 * bright)
        b = int(255)
        return (min(255, r), min(255, g), min(255, b))

    def _compute_offsets(
        self,
        p: Particle,
        spd: float,
        pulse: float,
        mic: float,
        base_bright: float,
    ) -> tuple[float, float]:
        """상태별 극좌표 변형 후 직교 좌표."""
        t = self._t
        ang = p.base_angle
        rad = p.radius_norm * self._core_r

        breathe = 1.0 + pulse * math.sin(t * 1.4 + p.phase * 0.5)

        if self._state_name == "IDLE":
            ang += spd * 0.012 * p.speed
            rad *= breathe * (0.97 + 0.06 * math.sin(t * 0.9 + p.phase))

        elif self._state_name == "LISTENING":
            ang += spd * 0.018 * p.speed
            wave = mic * self._core_r * 0.14 * math.sin(t * 4.5 + p.phase)
            rad *= breathe
            rad += wave + mic * 10 * p.layer
            ang += mic * 0.08 * math.sin(t * 3 + p.phase)

        elif self._state_name == "PROCESSING":
            swirl = spd * 0.055 * (1.0 + 0.3 * p.layer)
            ang += swirl * p.speed + 0.02 * math.sin(t * 2 + p.radius_norm * 6.28)
            rad *= 0.92 + 0.12 * math.sin(t * 2.2 + p.phase) + pulse * 0.08
            rad *= 1.0 + 0.04 * math.sin(ang * 3 + t)

        elif self._state_name == "EXECUTING":
            flow = spd * 0.04
            ang += flow * p.speed
            rad *= 0.88 + 0.1 * math.sin(t * 3.5 + p.phase)
            conv = math.sin(t * 1.8) * 0.06 * self._core_r
            # 특정 방향(우측 상단)으로 흐름
            extra_x = conv * 0.55 * (p.layer + 1)
            extra_y = -conv * 0.35 * (p.layer + 1)
            ox = rad * math.cos(ang) * breathe + extra_x
            oy = rad * math.sin(ang) * breathe + extra_y
            return (ox, oy)

        elif self._state_name == "RESPONDING":
            amp = self._audio_level if self._audio_level > 0.02 else 0.4 + 0.35 * math.sin(t * 2.2)
            beat = 1.0 + pulse * amp * math.sin(t * 3.5 + p.phase)
            ang += spd * 0.022 * p.speed
            rad *= beat * (0.94 + 0.08 * math.sin(t * 1.7))

        elif self._state_name == "MONITORING":
            orbit = spd * 0.015 * (1.0 if p.radius_norm > 0.55 else 0.35)
            ang += orbit * p.speed * (1 if p.layer else -0.6)
            rad *= 0.96 + 0.06 * math.sin(t * 1.1 + p.phase)

        elif self._state_name == "ALERTING":
            burst = 1.0 + pulse * 0.45 * max(0.0, math.sin(t * 7))
            ang += spd * 0.025 * math.sin(t * 5 + p.phase)
            rad *= burst * (0.9 + 0.18 * abs(math.sin(t * 6 + p.phase)))

        elif self._state_name == "ERROR":
            ang += spd * 0.02 * math.sin(t * 4 + p.phase) * (0.5 + base_bright * 0.5)
            rad *= 0.92 + 0.12 * math.sin(t * 5.7 + p.phase * 1.3)
            if math.sin(t * 13 + p.phase * 2) > 0.85:
                rad *= 0.82

        else:
            ang += spd * 0.01
            rad *= breathe

        ox = rad * math.cos(ang)
        oy = rad * math.sin(ang)
        return (ox, oy)
