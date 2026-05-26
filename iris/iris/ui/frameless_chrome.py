"""프레임리스 창 가장자리 리사이즈."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtWidgets import QApplication, QGridLayout, QSizePolicy, QWidget

_RESIZE_MARGIN = 8


def _cursor_for_edges(edges: Qt.Edge) -> Qt.CursorShape:
    has_l = bool(edges & Qt.Edge.LeftEdge)
    has_r = bool(edges & Qt.Edge.RightEdge)
    has_t = bool(edges & Qt.Edge.TopEdge)
    has_b = bool(edges & Qt.Edge.BottomEdge)
    if has_t and has_l or has_b and has_r:
        return Qt.CursorShape.SizeFDiagCursor
    if has_t and has_r or has_b and has_l:
        return Qt.CursorShape.SizeBDiagCursor
    if has_l or has_r:
        return Qt.CursorShape.SizeHorCursor
    if has_t or has_b:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.ArrowCursor


class _ResizeGrip(QWidget):
    """투명 리사이즈 핸들 — startSystemResize 위임."""

    def __init__(self, host: QWidget, edges: Qt.Edge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._edges = edges
        self.setCursor(QCursor(_cursor_for_edges(edges)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._host.isMaximized():
            handle = self._host.windowHandle()
            if handle is not None and handle.startSystemResize(self._edges):
                event.accept()
                return
        super().mousePressEvent(event)


class FramelessShell(QWidget):
    """콘텐츠를 감싸는 프레임리스 리사이즈 테두리."""

    def __init__(self, host: QWidget, margin: int = _RESIZE_MARGIN, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._margin = margin
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(0)
        self._center_slot: tuple[int, int] = (1, 1)

    def set_center_widget(self, content: QWidget) -> None:
        """본문 위젯을 중앙에 배치하고 가장자리 그립을 깐다."""
        m = self._margin
        grips: list[tuple[int, int, Qt.Edge, int | None, int | None]] = [
            (0, 0, Qt.Edge.TopEdge | Qt.Edge.LeftEdge, m, m),
            (0, 1, Qt.Edge.TopEdge, None, m),
            (0, 2, Qt.Edge.TopEdge | Qt.Edge.RightEdge, m, m),
            (1, 0, Qt.Edge.LeftEdge, m, None),
            (1, 2, Qt.Edge.RightEdge, m, None),
            (2, 0, Qt.Edge.BottomEdge | Qt.Edge.LeftEdge, m, m),
            (2, 1, Qt.Edge.BottomEdge, None, m),
            (2, 2, Qt.Edge.BottomEdge | Qt.Edge.RightEdge, m, m),
        ]
        for row, col, edges, w, h in grips:
            grip = _ResizeGrip(self._host, edges, self)
            if w is not None:
                grip.setFixedWidth(w)
            if h is not None:
                grip.setFixedHeight(h)
            if w is None:
                grip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if h is None:
                grip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            self._grid.addWidget(grip, row, col)
        content.setParent(self)
        self._grid.addWidget(content, *self._center_slot)


def center_on_screen(widget: QWidget) -> None:
    """주 모니터 가용 영역 중앙에 배치."""
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        widget.move(
            area.x() + max(0, (area.width() - widget.width()) // 2),
            area.y() + max(0, (area.height() - widget.height()) // 2),
        )
    except RuntimeError:
        pass
