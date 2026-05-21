"""실행 중인 창 목록 — 메인 창 내부 좌측 통합 사이드바.

설계:
- 별도 윈도우가 아닌 메인 창의 첫 번째 컬럼으로 내장
- 다크 테마 안에서 살짝 더 어두운 톤으로 시각적 분리
- 각 항목: [창 제목 버튼] [×]
- 항목 클릭 → 해당 창 포커스(MEDIUM_RISK)
- × 클릭 → WM_CLOSE 전송(HIGH_RISK, 정상 종료 루틴 따름)
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.automation.window_controller import (
    WindowInfo,
    close_window_by_hwnd,
    focus_and_place,
    focus_window_by_hwnd,
    list_visible_windows,
)

_REFRESH_MS = 2_500
_MAX_ITEMS = 30
_SIDEBAR_WIDTH = 220


class WindowListPanel(QWidget):
    """메인 창 좌측에 통합되는 실행 창 목록 사이드바."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowListPanel")
        self.setFixedWidth(_SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            "QWidget#WindowListPanel {"
            "  background: #060c1a;"
            "  border-right: 1px solid #1e293b;"
            "}"
            "QLabel#SidebarTitle {"
            "  color: #c4b5fd;"
            "  font-size: 12px;"
            "  font-weight: 700;"
            "  padding: 6px 4px 4px 6px;"
            "}"
            "QScrollArea { background: transparent; border: none; }"
            "QWidget#SidebarInner { background: transparent; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(4)

        title = QLabel("실행 중인 창")
        title.setObjectName("SidebarTitle")
        root.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._inner.setObjectName("SidebarInner")
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(3)
        self._inner_lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        self._prev_signature: tuple = ()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        try:
            wins = list_visible_windows()
        except Exception:
            wins = []
        wins = wins[:_MAX_ITEMS]

        # 변경 없으면 UI 갱신 생략
        signature = tuple((w.hwnd, w.title) for w in wins)
        if signature == self._prev_signature:
            return
        self._prev_signature = signature

        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not wins:
            hint = QLabel("실행 중인 창 없음")
            hint.setStyleSheet(
                "color: #475569; font-size: 11px; padding: 8px; background: transparent;"
            )
            self._inner_lay.addWidget(hint)
        else:
            for info in wins:
                self._inner_lay.addWidget(_make_row(info, self._on_focus, self._on_close))

        self._inner_lay.addStretch(1)

    def _on_focus(self, info: WindowInfo) -> None:
        ok = False
        if info.hwnd:
            ok = focus_window_by_hwnd(info.hwnd)
        if not ok:
            try:
                focus_and_place(info.title, info.left, info.top, info.width, info.height)
            except Exception:
                pass

    def _on_close(self, info: WindowInfo) -> None:
        if info.hwnd:
            close_window_by_hwnd(info.hwnd)
            QTimer.singleShot(300, self._refresh)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _make_row(info: WindowInfo, on_focus, on_close) -> QFrame:
    """[제목 버튼] [×] 한 줄."""
    fr = QFrame()
    fr.setStyleSheet(
        "QFrame {"
        "  background: #0f172a;"
        "  border: 1px solid #1e293b;"
        "  border-radius: 4px;"
        "}"
        "QFrame:hover { border-color: #4338ca; background: #1e1b4b; }"
    )

    h = QHBoxLayout(fr)
    h.setContentsMargins(2, 0, 2, 0)
    h.setSpacing(2)

    display = info.title if len(info.title) <= 24 else info.title[:22] + "…"
    btn = QPushButton(display)
    btn.setToolTip(info.title)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    btn.setStyleSheet(
        "QPushButton {"
        "  text-align: left;"
        "  padding: 4px 6px;"
        "  background: transparent;"
        "  border: none;"
        "  color: #cbd5e1;"
        "  font-size: 11px;"
        "}"
        "QPushButton:hover { color: #e0e7ff; }"
    )
    btn.clicked.connect(lambda _=False, i=info: on_focus(i))
    h.addWidget(btn, 1)

    x = QPushButton("×")
    x.setFixedSize(20, 20)
    x.setCursor(Qt.CursorShape.PointingHandCursor)
    x.setToolTip(f"창 닫기: {info.title}")
    x.setStyleSheet(
        "QPushButton {"
        "  background: transparent;"
        "  border: none;"
        "  color: #64748b;"
        "  font-size: 14px;"
        "  font-weight: 700;"
        "}"
        "QPushButton:hover { color: #ef4444; }"
    )
    x.clicked.connect(lambda _=False, i=info: on_close(i))
    h.addWidget(x, 0)

    return fr
