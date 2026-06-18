"""상단 Status Header — 모델·상태·TTS·백엔드 연결."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from iris.assistant.external_agent_adapter import external_backend_status_line
from iris.config.settings import Settings
from iris.core.state_machine import AppState
from iris.ui.theme_tokens import TOKENS

# DragTab 상태 2행 블록 높이 — 타이틀 텍스트·칩 행 정렬 기준
STATUS_BLOCK_HEIGHT = 36


def _status_dot_color(kind: str) -> str:
    """연결·상태 색상."""
    if kind in ("connected", "ready", "idle"):
        return TOKENS.success
    if kind in ("waiting", "processing", "listening", "responding"):
        return TOKENS.neon_cyan
    if kind in ("unavailable", "error"):
        return TOKENS.warning if kind == "unavailable" else TOKENS.error
    return TOKENS.text_muted


class _StatusChip(QWidget):
    """작은 색상 점 + 라벨."""

    def __init__(
        self,
        prefix: str,
        *,
        parent: QWidget | None = None,
        mono_value: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(STATUS_BLOCK_HEIGHT // 2)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(TOKENS.spacing_xs)

        self._dot = QLabel("●")
        self._dot.setObjectName("StatusDot")
        self._dot.setFixedWidth(10)
        row.addWidget(self._dot)

        self._prefix = QLabel(prefix.upper())
        self._prefix.setObjectName("StatusChipPrefix")
        row.addWidget(self._prefix)

        self._value = QLabel("-")
        self._value.setObjectName("StatusChipValueMono" if mono_value else "StatusChipValue")
        row.addWidget(self._value)

    def set_value(self, text: str, *, dot_kind: str = "idle") -> None:
        self._value.setText(text)
        color = _status_dot_color(dot_kind)
        self._dot.setStyleSheet(
            f"color: {color}; font-size: 8px; background: transparent; border: none;"
        )


class TopStatusHeader:
    """DragTab에 삽입할 상태 칩 묶음 — 별도 레이아웃 위젯 없이 행만 제공."""

    def __init__(self) -> None:
        # STATE / MODEL / TTS
        self._primary_row = QWidget()
        self._primary_row.setObjectName("TopStatusPrimaryRow")
        self._primary_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._primary_row.setFixedHeight(STATUS_BLOCK_HEIGHT // 2)
        row1 = QHBoxLayout(self._primary_row)
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(TOKENS.spacing_md)
        self._state_chip = _StatusChip("STATE")
        self._model_chip = _StatusChip("MODEL", mono_value=True)
        self._tts_chip = _StatusChip("TTS")
        for chip in (self._state_chip, self._model_chip, self._tts_chip):
            row1.addWidget(chip)

        # IRIS LOCAL / OPENCLAW / HERMES
        self._backend_row = QWidget()
        self._backend_row.setObjectName("TopStatusBackendRow")
        self._backend_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._backend_row.setFixedHeight(STATUS_BLOCK_HEIGHT // 2)
        row2 = QHBoxLayout(self._backend_row)
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(TOKENS.spacing_md)
        self._local_chip = _StatusChip("IRIS LOCAL")
        self._openclaw_chip = _StatusChip("OPENCLAW")
        self._hermes_chip = _StatusChip("HERMES")
        for chip in (self._local_chip, self._openclaw_chip, self._hermes_chip):
            row2.addWidget(chip)

        # StatusStrip 호환 — MainWindow가 참조하는 라벨
        self.model_label = self._model_chip._value  # noqa: SLF001
        self.status_label = self._state_chip._value  # noqa: SLF001
        self.tts_status_label = self._tts_chip._value  # noqa: SLF001

        self._local_chip.set_value("CONNECTED", dot_kind="connected")

    def primary_row(self) -> QWidget:
        """DragTab — STATE/MODEL/TTS 행."""
        return self._primary_row

    def backend_row(self) -> QWidget:
        """DragTab — IRIS LOCAL/OPENCLAW/HERMES 행 (primary 바로 아래)."""
        return self._backend_row

    def set_app_state(self, state: AppState) -> None:
        name = state.name
        kind = "idle"
        if state in (AppState.LISTENING,):
            kind = "listening"
        elif state in (AppState.PROCESSING, AppState.EXECUTING):
            kind = "processing"
        elif state in (AppState.RESPONDING,):
            kind = "responding"
        elif state in (AppState.ERROR, AppState.ALERTING):
            kind = "error"
        self._state_chip.set_value(name, dot_kind=kind)

    def set_model_name(self, name: str) -> None:
        display = name.strip() if name.strip() else "(unset)"
        self._model_chip.set_value(display, dot_kind="connected")

    def set_tts_status(self, text: str) -> None:
        lower = text.lower()
        kind = "ready"
        if "error" in lower or "fail" in lower:
            kind = "error"
        elif "busy" in lower or "speak" in lower:
            kind = "processing"
        self._tts_chip.set_value(text.upper(), dot_kind=kind)

    def refresh_backend_status(self, settings: Settings | None) -> None:
        """OpenClaw/Hermes 가용성 갱신."""
        line = external_backend_status_line(settings)
        oc = "UNAVAILABLE"
        hm = "UNAVAILABLE"
        if "OpenClaw (Connected)" in line:
            oc = "CONNECTED"
        if "Hermes (Connected)" in line:
            hm = "CONNECTED"
        self._openclaw_chip.set_value(
            oc,
            dot_kind="connected" if oc == "CONNECTED" else "unavailable",
        )
        self._hermes_chip.set_value(
            hm,
            dot_kind="connected" if hm == "CONNECTED" else "unavailable",
        )
