"""드래그 가능한 상단 탭 영역."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class DragTab(QWidget):
    """프레임리스 창 드래그용."""

    def __init__(self, parent_window: QWidget) -> None:
        super().__init__()
        self._win = parent_window
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        title = QLabel("Iris")
        title.setObjectName("DragTitle")
        btn_close = QPushButton("✕")
        btn_close.setFixedWidth(36)
        btn_close.clicked.connect(parent_window.close)
        lay.addWidget(btn_close)
        self._drag_pos = None

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(e)
