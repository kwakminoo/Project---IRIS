"""드래그 가능한 상단 탭 영역."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


def _win_ctrl_button(text: str, tooltip: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("WinCtrl")
    btn.setToolTip(tooltip)
    btn.setFixedSize(36, 28)
    return btn


class DragTab(QWidget):
    """프레임리스 창 드래그·창 제어 버튼."""

    settings_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()

    def __init__(self, parent_window: QWidget) -> None:
        super().__init__()
        self._win = parent_window
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        title = QLabel("Iris")
        title.setObjectName("DragTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(title)
        lay.addStretch(1)

        # 우측: [ − ][ □ ][ ✕ ] 가로 한 줄, 설정(⚙)은 ✕ 아래
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)
        self._btn_min = _win_ctrl_button("−", "창 내리기")
        self._btn_max = _win_ctrl_button("□", "전체 화면")
        self._btn_close = _win_ctrl_button("✕", "닫기")
        self._btn_settings = _win_ctrl_button("⚙", "설정")
        align_top = Qt.AlignmentFlag.AlignTop
        ctrl_row.addWidget(self._btn_min, alignment=align_top)
        ctrl_row.addWidget(self._btn_max, alignment=align_top)

        close_stack = QVBoxLayout()
        close_stack.setSpacing(2)
        close_stack.setContentsMargins(0, 0, 0, 0)
        close_stack.addWidget(
            self._btn_close,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        close_stack.addWidget(
            self._btn_settings,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        close_wrap = QWidget()
        close_wrap.setLayout(close_stack)
        ctrl_row.addWidget(close_wrap, alignment=align_top)

        lay.addLayout(ctrl_row)

        self._btn_min.clicked.connect(self.minimize_clicked.emit)
        self._btn_max.clicked.connect(self.maximize_clicked.emit)
        self._btn_close.clicked.connect(parent_window.close)
        self._btn_settings.clicked.connect(self.settings_clicked.emit)
        self._drag_pos = None

    def set_maximized(self, maximized: bool) -> None:
        """전체화면/복원 버튼 표시 갱신."""
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
