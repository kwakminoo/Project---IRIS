"""실행 중인 창 목록 — HUD 스타일 좌측 사이드바."""

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
    get_active_window_title,
    list_visible_windows,
)
from iris.ui.glass_panel import wrap_glass_panel
from iris.ui.section_header import apply_section_panel_layout, make_section_header
from iris.ui.theme_tokens import TOKENS

_REFRESH_MS = 2_500
_MAX_ITEMS = 30


def _parse_window_title(title: str) -> tuple[str, str]:
    """창 제목 → (앱명, 문서/부제)."""
    if " - " in title:
        doc, app = title.rsplit(" - ", 1)
        if app.strip():
            return app.strip(), doc.strip()
    return title.strip(), ""


def _window_type_icon(app_name: str, title: str) -> str:
    """간단 유형 아이콘 (텍스트)."""
    blob = f"{app_name} {title}".lower()
    if any(k in blob for k in ("chrome", "edge", "firefox", "brave")):
        return "🌐"
    if any(k in blob for k in ("cursor", "code", "visual studio", "theia")):
        return "⌨"
    if any(k in blob for k in ("discord", "slack", "teams")):
        return "💬"
    if any(k in blob for k in ("steam", "league", "game")):
        return "🎮"
    if any(k in blob for k in ("terminal", "powershell", "cmd", "pwsh")):
        return "▸"
    return "▢"


class WindowListPanel(QWidget):
    """메인 창 좌측에 통합되는 실행 창 목록 — 사이버스페이스 HUD."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowListPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        inner = QWidget()
        inner.setObjectName("WindowListPanelInner")
        root = QVBoxLayout(inner)
        apply_section_panel_layout(root)

        root.addWidget(
            make_section_header("RUNNING WINDOWS", title_object_name="SidebarTitle")
        )

        self._scroll = QScrollArea()
        self._scroll.setObjectName("PanelScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._inner.setObjectName("SidebarInner")
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(2)
        self._inner_lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(wrap_glass_panel(inner))

        self._selected_hwnd: int | None = None
        self._prev_signature: tuple = ()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _refresh(self) -> None:
        try:
            wins = list_visible_windows()
        except Exception:
            wins = []
        wins = wins[:_MAX_ITEMS]
        active_title = ""
        try:
            active_title = get_active_window_title()
        except Exception:
            pass

        signature = tuple((w.hwnd, w.title, active_title) for w in wins)
        if signature == self._prev_signature:
            return
        self._prev_signature = signature

        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not wins:
            hint = QLabel("No active windows")
            hint.setObjectName("PanelEmptyHint")
            hint.setStyleSheet(
                f"color: {TOKENS.text_muted}; font-size: {TOKENS.font_size_caption};"
                f" padding: {TOKENS.spacing_sm}px {TOKENS.spacing_xs}px;"
                " background: transparent;"
            )
            self._inner_lay.addWidget(hint)
        else:
            for info in wins:
                is_active = bool(active_title) and (
                    info.title == active_title
                    or active_title in info.title
                    or info.title in active_title
                )
                self._inner_lay.addWidget(
                    _make_row(
                        info,
                        is_active=is_active,
                        selected_hwnd=self._selected_hwnd,
                        on_focus=self._on_focus,
                        on_close=self._on_close,
                    )
                )

        self._inner_lay.addStretch(1)

    def _on_select(self, info: WindowInfo) -> None:
        self._selected_hwnd = info.hwnd or None
        self._prev_signature = ()
        self._refresh()

    def _on_focus(self, info: WindowInfo) -> None:
        self._on_select(info)
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


def _make_row(
    info: WindowInfo,
    *,
    is_active: bool,
    selected_hwnd: int | None,
    on_focus,
    on_close,
) -> QFrame:
    """HUD 리스트 행 — 아이콘·앱명·제목·활성 표시."""
    fr = QFrame()
    fr.setObjectName("HudWindowRow")
    is_selected = selected_hwnd and info.hwnd == selected_hwnd
    if is_active or is_selected:
        fr.setProperty("active", True)
    else:
        fr.setProperty("active", False)
    fr.style().unpolish(fr)
    fr.style().polish(fr)

    app_name, subtitle = _parse_window_title(info.title)
    icon = _window_type_icon(app_name, info.title)

    h = QHBoxLayout(fr)
    h.setContentsMargins(6, 5, 4, 5)
    h.setSpacing(TOKENS.spacing_sm)

    icon_lbl = QLabel(icon)
    icon_lbl.setFixedWidth(18)
    icon_lbl.setStyleSheet(
        f"font-size: {TOKENS.font_size_body}; background: transparent; border: none;"
    )
    h.addWidget(icon_lbl)

    text_col = QVBoxLayout()
    text_col.setSpacing(1)
    text_col.setContentsMargins(0, 0, 0, 0)

    app_row = QHBoxLayout()
    app_row.setSpacing(TOKENS.spacing_xs)
    app_lbl = QLabel(app_name)
    app_lbl.setObjectName("HudWindowAppName")
    app_lbl.setToolTip(info.title)
    app_lbl.setStyleSheet(
        f"color: {TOKENS.text_primary}; font-size: {TOKENS.font_size_caption};"
        " font-weight: 600; background: transparent; border: none;"
    )
    app_row.addWidget(app_lbl, 1)
    if is_active:
        dot = QLabel("● active")
        dot.setObjectName("HudWindowActiveBadge")
        dot.setStyleSheet(
            f"color: {TOKENS.neon_cyan}; font-size: {TOKENS.font_size_micro};"
            " background: transparent; border: none;"
        )
        app_row.addWidget(dot)
    text_col.addLayout(app_row)

    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setObjectName("HudWindowSubtitle")
        sub_lbl.setToolTip(info.title)
        sub_lbl.setWordWrap(False)
        sub_lbl.setStyleSheet(
            f"color: {TOKENS.text_muted}; font-size: {TOKENS.font_size_caption};"
            " background: transparent; border: none;"
        )
        # 말줄임 — QLabel elide
        from PyQt6.QtGui import QFontMetrics

        metrics = QFontMetrics(sub_lbl.font())
        sub_lbl.setText(metrics.elidedText(subtitle, Qt.TextElideMode.ElideRight, 160))
        text_col.addWidget(sub_lbl)

    text_wrap = QWidget()
    text_wrap.setLayout(text_col)
    text_wrap.setCursor(Qt.CursorShape.PointingHandCursor)
    text_wrap.mousePressEvent = lambda _e, i=info: on_focus(i)  # type: ignore[method-assign]
    h.addWidget(text_wrap, 1)

    x = QPushButton("×")
    x.setObjectName("HudWindowClose")
    x.setFixedSize(22, 22)
    x.setCursor(Qt.CursorShape.PointingHandCursor)
    x.setToolTip(f"Close window: {info.title}")
    x.clicked.connect(lambda _=False, i=info: on_close(i))
    h.addWidget(x, 0)

    return fr
