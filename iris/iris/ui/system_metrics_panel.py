"""시스템 CPU·GPU·메모리 — HUD 스타일 표시."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from iris.ui.glass_panel import wrap_glass_panel
from iris.ui.section_header import apply_section_panel_layout, make_section_header
from iris.system.metrics_snapshot import MetricsSnapshot
from iris.ui.theme_tokens import TOKENS

_MIN_BAR_VALUE = 2  # 0%일 때도 트랙이 보이도록


class _MetricRow(QWidget):
    """라벨 + 퍼센트 + progress bar."""

    def __init__(self, name: str, fill_color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HudMetricRow")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, TOKENS.spacing_sm)
        lay.setSpacing(TOKENS.spacing_xs)

        header = QHBoxLayout()
        self._name = QLabel(name)
        self._name.setObjectName("HudMetricName")
        self._value = QLabel("0%")
        self._value.setObjectName("HudMetricValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._name)
        header.addStretch(1)
        header.addWidget(self._value)
        lay.addLayout(header)

        self._bar = QProgressBar()
        self._bar.setObjectName("HudMetricBar")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(
            f"""
            QProgressBar#HudMetricBar {{
                background: {TOKENS.metric_track};
                border: none;
                border-radius: {TOKENS.radius_sm}px;
            }}
            QProgressBar#HudMetricBar::chunk {{
                background: {fill_color};
                border-radius: {TOKENS.radius_sm}px;
                min-width: 4px;
            }}
            """
        )
        lay.addWidget(self._bar)
        self._fill_color = fill_color

    def apply(self, percent: float | None, *, label: str | None = None) -> None:
        if label is not None:
            self._name.setText(label)
        if percent is None:
            self._value.setText("N/A")
            self._bar.setValue(_MIN_BAR_VALUE)
            return
        pct = max(0.0, min(100.0, float(percent)))
        self._value.setText(f"{pct:.0f}%")
        bar_val = max(_MIN_BAR_VALUE, int(round(pct))) if pct > 0 else _MIN_BAR_VALUE
        self._bar.setValue(bar_val)


class SystemMetricsPanel(QWidget):
    """실시간 시스템 리소스 — 얇은 HUD 메트릭 바."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SystemMetricsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        inner = QWidget()
        inner.setObjectName("SystemMetricsPanelInner")
        lay = QVBoxLayout(inner)
        apply_section_panel_layout(lay)
        lay.addWidget(
            make_section_header("SYSTEM METRICS", title_object_name="SidebarTitle")
        )

        self._cpu = _MetricRow("CPU", TOKENS.metric_fill_cpu)
        self._gpu = _MetricRow("GPU", TOKENS.metric_fill_gpu)
        self._mem = _MetricRow("MEMORY", TOKENS.metric_fill_mem)
        for row in (self._cpu, self._gpu, self._mem):
            lay.addWidget(row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(wrap_glass_panel(inner))

    def apply_snapshot(self, snap: MetricsSnapshot) -> None:
        self._cpu.apply(snap.cpu_percent)
        self._mem.apply(snap.memory_percent)
        if snap.gpu_percent is None:
            self._gpu.apply(None, label=snap.gpu_label.upper())
        else:
            self._gpu.apply(snap.gpu_percent, label="GPU")
