"""상단 Status Header — 모델·상태·TTS·백엔드 연결."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from iris.assistant.external_agent_adapter import external_backend_status_line
from iris.config.settings import Settings
from iris.core.state_machine import AppState
from iris.ui.theme_tokens import TOKENS


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
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(TOKENS.spacing_xs)

        self._dot = QLabel("●")
        self._dot.setObjectName("StatusDot")
        self._dot.setFixedWidth(12)
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
            f"color: {color}; font-size: 9px; background: transparent; border: none;"
        )


class TopStatusHeader(QFrame):
    """Assistant/IDE 공용 상단 상태 헤더."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopStatusHeader")
        root = QVBoxLayout(self)
        root.setContentsMargins(
            TOKENS.spacing_xs,
            TOKENS.spacing_sm,
            TOKENS.spacing_xs,
            TOKENS.spacing_sm,
        )
        root.setSpacing(TOKENS.spacing_xs)

        row1 = QHBoxLayout()
        row1.setSpacing(TOKENS.spacing_lg)
        self._state_chip = _StatusChip("STATE")
        self._model_chip = _StatusChip("MODEL", mono_value=True)
        self._tts_chip = _StatusChip("TTS")
        for chip in (self._state_chip, self._model_chip, self._tts_chip):
            row1.addWidget(chip)
        row1.addStretch(1)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(TOKENS.spacing_lg)
        self._local_chip = _StatusChip("IRIS LOCAL")
        self._openclaw_chip = _StatusChip("OPENCLAW")
        self._hermes_chip = _StatusChip("HERMES")
        for chip in (self._local_chip, self._openclaw_chip, self._hermes_chip):
            row2.addWidget(chip)
        row2.addStretch(1)
        root.addLayout(row2)

        # StatusStrip 호환 — MainWindow가 참조하는 라벨
        self.model_label = self._model_chip._value  # noqa: SLF001
        self.status_label = self._state_chip._value  # noqa: SLF001
        self.tts_status_label = self._tts_chip._value  # noqa: SLF001

        self._local_chip.set_value("CONNECTED", dot_kind="connected")

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
