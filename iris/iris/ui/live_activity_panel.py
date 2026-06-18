"""Live Activity — 구체 아래 상태·최근 활동 요약."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from iris.core.activity_privacy import prepare_activity_line
from iris.core.state_machine import AppState
from iris.ui.glass_panel import wrap_glass_panel
from iris.ui.theme_tokens import TOKENS

_MAX_RECENT = 4
_STATE_MESSAGES: dict[str, tuple[str, str]] = {
    "IDLE": ("Idle", "IRIS is waiting for a command."),
    "LISTENING": ("Listening", "Capturing your voice…"),
    "PROCESSING": ("Processing", "Analyzing the active workspace…"),
    "EXECUTING": ("Executing", "Running automation steps…"),
    "RESPONDING": ("Responding", "Composing and speaking a reply…"),
    "MONITORING": ("Monitoring", "Watching registered targets…"),
    "ALERTING": ("Alert", "An event needs your attention."),
    "ERROR": ("Error", "Something went wrong — check logs."),
}


class UiActivityRelay(QObject):
    """push_activity_line 싱크를 Qt 메인 스레드로 안전하게 넘김."""

    line = pyqtSignal(str)

    def push(self, message: str) -> None:
        safe = prepare_activity_line(message)
        if safe:
            self.line.emit(safe)


class LiveActivityPanel(QWidget):
    """
    Visualizer(구체)와 Command Dock 사이 — 상태 + 최근 활동 로그.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LiveActivityPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(88)
        self.setMaximumHeight(120)

        inner = QWidget()
        inner.setObjectName("LiveActivityPanelInner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(
            TOKENS.spacing_md,
            TOKENS.spacing_sm,
            TOKENS.spacing_md,
            TOKENS.spacing_sm,
        )
        lay.setSpacing(TOKENS.spacing_xs)

        hdr = QLabel("LIVE ACTIVITY")
        hdr.setObjectName("LiveActivityTitle")
        lay.addWidget(hdr)

        self._state_row = QLabel("● Idle")
        self._state_row.setObjectName("LiveActivityState")
        lay.addWidget(self._state_row)

        self._detail = QLabel("IRIS is waiting for a command.")
        self._detail.setObjectName("LiveActivityDetail")
        self._detail.setWordWrap(True)
        lay.addWidget(self._detail)

        self._recent: deque[str] = deque(maxlen=_MAX_RECENT)
        self._recent_label = QLabel("")
        self._recent_label.setObjectName("LiveActivityRecent")
        self._recent_label.setWordWrap(True)
        lay.addWidget(self._recent_label)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(wrap_glass_panel(inner))

        self._app_state = AppState.IDLE

    def set_app_state(self, state: AppState) -> None:
        self._app_state = state
        title, detail = _STATE_MESSAGES.get(state.name, (state.name, ""))
        self._state_row.setText(f"● {title}")
        self._detail.setText(detail)
        if state is AppState.IDLE and not self._recent:
            self._recent_label.setText("")

    def enqueue_typed_line(self, line: str) -> None:
        """메인 스레드 — 최근 활동 목록에 추가."""
        if not line:
            return
        self._recent.append(line.strip())
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        if not self._recent:
            if self._app_state is AppState.IDLE:
                self._recent_label.setText("")
            else:
                self._recent_label.setText("")
            return
        bullets = "\n".join(f"· {ln[:120]}" for ln in list(self._recent)[-_MAX_RECENT:])
        self._recent_label.setText(bullets)

    def clear_for_idle(self) -> None:
        """Idle 복귀 시 최근 로그 축소."""
        self._recent.clear()
        self._recent_label.setText("")
        self.set_app_state(AppState.IDLE)
