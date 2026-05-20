"""채팅 입력 하단 마이크 주파수(웨이브폼) 표시 — 다층 대칭 파형."""

from __future__ import annotations

import math
from collections import deque

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from iris.audio.mic_level import speech_rms_to_display_level

# 샘플 버퍼 용량 (약 30Hz × 6초)
_SAMPLE_CAPACITY = 180
# 애니메이션 프레임 간격
_FRAME_INTERVAL_MS = 33  # ~30fps
# 파형 레이어 수
_NUM_LAYERS = 7
# 위상 오프셋 (레이어마다 다른 타이밍)
_PHASE_OFFSETS = [0.0, 0.4, 0.8, 1.3, 1.7, 2.2, 2.7]
# 주파수 배율 (레이어마다 다른 밀도)
_FREQ_MULTIPLIERS = [1.0, 1.3, 1.7, 2.1, 2.6, 3.2, 3.9]
# 진폭 배율 (가운데 레이어가 가장 큼)
_AMP_SCALES = [0.45, 0.60, 0.78, 1.0, 0.78, 0.60, 0.45]

# 색상 팔레트: 바깥→안쪽 (어두운 남색 → 밝은 시안/흰)
_LAYER_COLORS = [
    (30, 64, 175, 90),    # 인디고-900 투명
    (37, 99, 235, 110),   # 블루-600
    (59, 130, 246, 140),  # 블루-500
    (147, 197, 253, 200), # 블루-300 (중심 — 가장 밝음)
    (59, 130, 246, 140),  # 블루-500
    (37, 99, 235, 110),   # 블루-600
    (30, 64, 175, 90),    # 인디고-900 투명
]

# 발화 감지 시 색상 (밝은 시안 계열)
_LAYER_COLORS_ACTIVE = [
    (14, 116, 144, 100),  # 시안-800
    (6, 182, 212, 130),   # 시안-500
    (34, 211, 238, 170),  # 시안-400
    (207, 250, 254, 240), # 시안-50 (중심 — 거의 흰색)
    (34, 211, 238, 170),  # 시안-400
    (6, 182, 212, 130),   # 시안-500
    (14, 116, 144, 100),  # 시안-800
]


class MicWaveformBar(QWidget):
    """
    입력칸 아래 다층 대칭 주파수 시각화.
    - 참조 이미지처럼 중심선 기준 상하 대칭으로 여러 겹의 파형을 그림
    - 마이크 레벨에 따라 진폭·색상 강도 변화
    - 무음 시에도 잔잔한 파형 애니메이션 유지
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MicWaveformBar")
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._samples: deque[float] = deque(maxlen=_SAMPLE_CAPACITY)
        self._level = 0.0
        self._smooth_level = 0.0  # 부드러운 보간 레벨
        self._threshold_display = speech_rms_to_display_level(0.018)
        self._phase = 0.0  # 글로벌 위상 (애니메이션 드라이버)
        self._mic_live = False

        # 프레임 타이머 — 부드러운 애니메이션
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(_FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start()

    def set_threshold_rms(self, speech_rms: float) -> None:
        self._threshold_display = speech_rms_to_display_level(speech_rms)
        self.update()

    def set_level(self, level: float) -> None:
        incoming = min(1.0, max(0.0, level))
        self._mic_live = True
        # 피크 유지 + 부드러운 감쇠
        self._level = max(incoming, self._level * 0.85)
        self._samples.append(self._level)
        self.update()

    def _on_frame(self) -> None:
        """프레임마다 위상 전진 + 부드러운 레벨 보간."""
        self._phase += 0.08
        if self._phase > math.pi * 200:
            self._phase -= math.pi * 200

        # 부드러운 보간 (lerp)
        target = self._level if self._mic_live else 0.0
        self._smooth_level += (target - self._smooth_level) * 0.12

        # 자연 감쇠
        if self._level > 0.001:
            self._level *= 0.92
        else:
            self._level = 0.0

        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin_x = 16
        inner_w = max(1, w - margin_x * 2)
        mid_y = h / 2.0

        # 활성도에 따른 최대 진폭
        base_amp = h * 0.15  # 무음 시 최소 파형 높이
        active_amp = h * 0.42  # 최대 파형 높이
        current_amp = base_amp + (active_amp - base_amp) * self._smooth_level

        # 발화 여부
        above_threshold = self._smooth_level >= self._threshold_display * 0.5

        # 각 레이어 그리기 (바깥→안쪽 순서로 — 안쪽이 위에)
        for layer_idx in range(_NUM_LAYERS):
            phase_offset = _PHASE_OFFSETS[layer_idx]
            freq_mult = _FREQ_MULTIPLIERS[layer_idx]
            amp_scale = _AMP_SCALES[layer_idx]

            # 색상 선택
            if above_threshold:
                r, g, b, a = _LAYER_COLORS_ACTIVE[layer_idx]
            else:
                r, g, b, a = _LAYER_COLORS[layer_idx]

            # 파형 경로 생성 (상단)
            path_top = QPainterPath()
            path_bottom = QPainterPath()

            # 해상도: 2px당 1포인트
            num_points = max(60, inner_w // 2)
            step = inner_w / num_points

            for i in range(num_points + 1):
                x = margin_x + i * step
                # 다중 사인파 합성으로 자연스러운 주파수 형태
                t = i / num_points
                wave = (
                    math.sin(t * math.pi * 4.0 * freq_mult + self._phase + phase_offset) * 0.5
                    + math.sin(t * math.pi * 7.0 * freq_mult + self._phase * 1.3 + phase_offset * 1.5) * 0.3
                    + math.sin(t * math.pi * 11.0 * freq_mult + self._phase * 0.7 + phase_offset * 2.0) * 0.2
                )

                # 양쪽 끝을 자연스럽게 0으로 페이드 (가우시안 윈도우)
                envelope = math.exp(-((t - 0.5) ** 2) / 0.08)

                y_offset = wave * current_amp * amp_scale * envelope

                # 상단 파형
                y_top = mid_y - abs(y_offset)
                # 하단 파형 (대칭)
                y_bottom = mid_y + abs(y_offset)

                if i == 0:
                    path_top.moveTo(x, y_top)
                    path_bottom.moveTo(x, y_bottom)
                else:
                    path_top.lineTo(x, y_top)
                    path_bottom.lineTo(x, y_bottom)

            # 펜 설정 — 얇은 선
            color = QColor(r, g, b, a)
            pen = QPen(color)
            pen_width = 0.3 + amp_scale * 0.2
            pen.setWidthF(pen_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)

            # 상단·하단 파형 그리기
            p.drawPath(path_top)
            p.drawPath(path_bottom)

        # 중심 글로우 라인 (은은한 하이라이트)
        if self._smooth_level > 0.02:
            glow_alpha = int(40 + 60 * self._smooth_level)
            glow_color = QColor(191, 219, 254, glow_alpha)
            glow_pen = QPen(glow_color)
            glow_pen.setWidthF(1.0)
            p.setPen(glow_pen)
            p.drawLine(int(margin_x), int(mid_y), int(margin_x + inner_w), int(mid_y))

        p.end()
