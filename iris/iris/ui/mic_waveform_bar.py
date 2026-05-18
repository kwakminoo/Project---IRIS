"""채팅 입력 하단 마이크 주파수(웨이브폼) 표시."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from iris.audio.mic_level import speech_rms_to_display_level

# 스크롤 버퍼 길이 (약 10Hz × 18초)
_SAMPLE_CAPACITY = 180
# 심전도 스윕 — 왼쪽→오른쪽 (ms당 진행량)
_SWEEP_INTERVAL_MS = 40
_SWEEP_STEP = 0.018


class MicWaveformBar(QWidget):
    """
    입력칸 아래 푸른 주파수 선.
    - 임계 이상: 발화·인식 피드백용 파형 진폭 강조
    - 임계 미만: 잔여 소음(외부 소리)도 옅게 표시
    - 무음 시: 기준선 + 투명 스윕 포인트로 '동작 중' 표시
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MicWaveformBar")
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._samples: deque[float] = deque(maxlen=_SAMPLE_CAPACITY)
        self._level = 0.0
        self._threshold_display = speech_rms_to_display_level(0.018)
        self._sweep = 0.0
        self._mic_live = False

        self._sweep_timer = QTimer(self)
        self._sweep_timer.setInterval(_SWEEP_INTERVAL_MS)
        self._sweep_timer.timeout.connect(self._advance_sweep)
        self._sweep_timer.start()

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(500)
        self._idle_timer.timeout.connect(self._decay_level)
        self._idle_timer.start()

    def set_threshold_rms(self, speech_rms: float) -> None:
        self._threshold_display = speech_rms_to_display_level(speech_rms)
        self.update()

    def set_level(self, level: float) -> None:
        incoming = min(1.0, max(0.0, level))
        self._mic_live = True
        # 짧은 피크도 보이게 — 설정 게이지와 동일한 감쇠
        self._level = max(incoming, self._level * 0.82)
        self._samples.append(self._level)
        self.update()

    def _decay_level(self) -> None:
        if self._level > 0.001:
            self._level *= 0.75
            self._samples.append(self._level)
            self.update()
        elif not self._mic_live:
            self.update()

    def _advance_sweep(self) -> None:
        self._sweep += _SWEEP_STEP
        if self._sweep > 1.0:
            self._sweep -= 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin_x, margin_y = 10, 8
        inner_w = max(1, w - margin_x * 2)
        inner_h = max(1, h - margin_y * 2)
        mid_y = margin_y + inner_h / 2.0
        amp = inner_h * 0.42

        # 기준 푸른 선 (무음·대기)
        base_pen = QPen(QColor(37, 99, 235, 140))
        base_pen.setWidthF(1.5)
        p.setPen(base_pen)
        p.drawLine(int(margin_x), int(mid_y), int(margin_x + inner_w), int(mid_y))

        # 인식 감도 임계 — 옅은 점선
        thresh_y = mid_y - self._threshold_display * amp
        dash = QPen(QColor(251, 191, 36, 120))
        dash.setStyle(Qt.PenStyle.DashLine)
        dash.setWidthF(1.0)
        p.setPen(dash)
        p.drawLine(int(margin_x), int(thresh_y), int(margin_x + inner_w), int(thresh_y))

        # 주파수 파형
        if len(self._samples) >= 2:
            path = QPainterPath()
            count = len(self._samples)
            step = inner_w / max(1, count - 1)
            for i, sample in enumerate(self._samples):
                x = margin_x + i * step
                y = mid_y - sample * amp
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            above = self._level >= self._threshold_display
            wave_color = QColor(34, 211, 238, 230) if above else QColor(59, 130, 246, 110)
            wave_pen = QPen(wave_color)
            wave_pen.setWidthF(2.0 if above else 1.5)
            wave_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            wave_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(wave_pen)
            p.drawPath(path)

        # 심전도형 스윕 — 투명 포인트가 왼쪽→오른쪽 이동
        sweep_x = margin_x + self._sweep * inner_w
        grad = QLinearGradient(sweep_x - 14, 0, sweep_x + 14, 0)
        grad.setColorAt(0.0, QColor(96, 165, 250, 0))
        grad.setColorAt(0.45, QColor(147, 197, 253, 55))
        grad.setColorAt(0.5, QColor(191, 219, 254, 90))
        grad.setColorAt(0.55, QColor(147, 197, 253, 55))
        grad.setColorAt(1.0, QColor(96, 165, 250, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        band_top = margin_y
        band_h = inner_h
        p.drawRect(int(sweep_x - 14), int(band_top), 28, int(band_h))

        dot = QColor(191, 219, 254, 100)
        p.setBrush(dot)
        p.drawEllipse(QPointF(sweep_x, mid_y), 3.5, 3.5)

        p.end()
