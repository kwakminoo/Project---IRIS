"""Draggable top chrome with stable window controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget


def _win_ctrl_button(text: str, tooltip: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("WinCtrl")
    btn.setToolTip(tooltip)
    btn.setFixedSize(34, 28)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


class DragTab(QWidget):
    """Frameless title bar with drag handling and window controls."""

    settings_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()

    def __init__(self, parent_window: QWidget) -> None:
        super().__init__()
        self._win = parent_window
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        title = QLabel("IRIS")
        title.setObjectName("DragTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(title)
        lay.addStretch(1)

        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(0, 0, 0, 0)
        ctrl_row.setSpacing(4)
        ctrl_row.setSizeConstraint(QHBoxLayout.SizeConstraint.SetFixedSize)

        self._btn_settings = _win_ctrl_button("⚙", "설정")
        self._btn_min = _win_ctrl_button("−", "창 내리기")
        self._btn_max = _win_ctrl_button("□", "전체 화면")
        self._btn_close = _win_ctrl_button("×", "닫기")

        for btn in (self._btn_settings, self._btn_min, self._btn_max, self._btn_close):
            ctrl_row.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(ctrl_row)

        self._btn_min.clicked.connect(self.minimize_clicked.emit)
        self._btn_max.clicked.connect(self.maximize_clicked.emit)
        self._btn_close.clicked.connect(parent_window.close)
        self._btn_settings.clicked.connect(self.settings_clicked.emit)
        self._drag_pos = None

    def set_maximized(self, maximized: bool) -> None:
        """Update maximize/restore button state."""
        if maximized:
            self._btn_max.setText("❐")
            self._btn_max.setToolTip("창 복원")
        else:
            self._btn_max.setText("□")
            self._btn_max.setToolTip("전체 화면")

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if not self._win.isMaximized():
                self._win.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.maximize_clicked.emit()
        super().mouseDoubleClickEvent(e)
