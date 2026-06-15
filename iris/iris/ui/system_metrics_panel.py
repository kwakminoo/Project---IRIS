"""시스템 CPU·GPU·메모리 — HUD 스타일 표시."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from iris.system.metrics_snapshot import MetricsSnapshot
from iris.ui.theme_tokens import TOKENS


class SystemMetricsPanel(QWidget):
    """실시간 시스템 리소스 — 얇은 HUD 메트릭 바."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SystemMetricsPanel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 4)
        lay.setSpacing(8)

        hdr = QLabel("SYSTEM METRICS")
        hdr.setObjectName("HudSectionTitle")
        lay.addWidget(hdr)

        self._cpu_label = QLabel("CPU")
        self._cpu_bar = self._make_bar(TOKENS.metric_fill_cpu)
        self._gpu_label = QLabel("GPU")
        self._gpu_bar = self._make_bar(TOKENS.metric_fill_gpu)
        self._mem_label = QLabel("MEM")
        self._mem_bar = self._make_bar(TOKENS.metric_fill_mem)

        for label, bar in (
            (self._cpu_label, self._cpu_bar),
            (self._gpu_label, self._gpu_bar),
            (self._mem_label, self._mem_bar),
        ):
            label.setStyleSheet(
                f"color: {TOKENS.text_hud_label}; font-size: {TOKENS.font_size_micro};"
                " letter-spacing: 0.8px; background: transparent;"
            )
            lay.addWidget(label)
            lay.addWidget(bar)

    def _make_bar(self, fill_color: str) -> QProgressBar:
        bar = QProgressBar()
        bar.setObjectName("HudMetricBar")
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            f"""
            QProgressBar#HudMetricBar {{
                background: {TOKENS.metric_track};
                border: none;
                border-radius: 2px;
                height: 6px;
                text-align: right;
                color: {TOKENS.text_secondary};
                font-size: {TOKENS.font_size_micro};
            }}
            QProgressBar#HudMetricBar::chunk {{
                background: {fill_color};
                border-radius: 2px;
            }}
            """
        )
        return bar

    def apply_snapshot(self, snap: MetricsSnapshot) -> None:
        self._cpu_bar.setValue(int(round(snap.cpu_percent)))
        self._cpu_bar.setFormat(f"{snap.cpu_percent:.0f}%")
        self._mem_bar.setValue(int(round(snap.memory_percent)))
        self._mem_bar.setFormat(f"{snap.memory_percent:.0f}%")
        if snap.gpu_percent is None:
            self._gpu_bar.setValue(0)
            self._gpu_bar.setFormat("N/A")
            self._gpu_label.setText(snap.gpu_label.upper())
        else:
            self._gpu_bar.setValue(int(round(snap.gpu_percent)))
            self._gpu_bar.setFormat(f"{snap.gpu_percent:.0f}%")
            self._gpu_label.setText("GPU")
