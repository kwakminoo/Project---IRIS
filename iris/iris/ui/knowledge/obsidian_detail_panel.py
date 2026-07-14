"""Obsidian 좌측 상세 — 마크다운 렌더 미리보기 + 2D/3D 전환."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from iris.core.markdown_text import markdown_to_chat_html
from iris.ui.section_header import (
    SECTION_TITLE_LINE_GAP,
    apply_section_panel_layout,
)
from iris.ui.theme_tokens import TOKENS


class ObsidianDetailPanel(QWidget):
    """상단: NOTE + 2D/3D / 하단: 마크다운 본문."""

    view_mode_changed = pyqtSignal(str)  # "2d" | "3d"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianDetailPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        apply_section_panel_layout(root)

        self._view_mode = "3d"
        self._header = self._build_header()
        root.addWidget(self._header, 0)

        self._path = QLabel("")
        self._path.setObjectName("ObsidianDetailPath")
        self._path.setWordWrap(True)
        self._path.setStyleSheet(
            f"color: {TOKENS.text_muted}; font-size: {TOKENS.font_size_micro};"
            " background: transparent; border: none;"
        )
        root.addWidget(self._path, 0)

        self._body = QTextBrowser()
        self._body.setObjectName("ObsidianPreviewBody")
        self._body.setOpenExternalLinks(True)
        self._body.setPlaceholderText("구체에서 노트를 선택하세요…")
        root.addWidget(self._body, 1)

        self.clear()

    def _build_header(self) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("SectionHeader")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SECTION_TITLE_LINE_GAP)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(TOKENS.spacing_xs)

        self._title = QLabel("NOTE")
        self._title.setObjectName("SidebarTitle")
        self._title.setStyleSheet("background: transparent; border: none;")
        row.addWidget(self._title, 1)

        self._btn_2d = self._make_mode_button("2D")
        self._btn_3d = self._make_mode_button("3D")
        self._btn_2d.clicked.connect(lambda: self.set_view_mode("2d"))
        self._btn_3d.clicked.connect(lambda: self.set_view_mode("3d"))
        row.addWidget(self._btn_2d, 0)
        row.addWidget(self._btn_3d, 0)
        lay.addLayout(row)

        line = QFrame()
        line.setObjectName("SectionUnderline")
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background: {TOKENS.panel_border}; border: none; max-height: 1px;"
        )
        lay.addWidget(line)

        self._sync_mode_buttons()
        return wrap

    def _make_mode_button(self, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("HudModeButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(22)
        btn.setMinimumWidth(32)
        btn.setStyleSheet("padding: 2px 8px;")  # 사이드바용 콤팩트
        return btn

    def view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode: str) -> None:
        """2d / 3d — 기본 3d."""
        name = "2d" if str(mode).strip().lower() == "2d" else "3d"
        if name == self._view_mode:
            self._sync_mode_buttons()
            return
        self._view_mode = name
        self._sync_mode_buttons()
        self.view_mode_changed.emit(name)

    def _sync_mode_buttons(self) -> None:
        self._btn_2d.setProperty("active", self._view_mode == "2d")
        self._btn_3d.setProperty("active", self._view_mode == "3d")
        for btn in (self._btn_2d, self._btn_3d):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def show_note(self, *, title: str, path: str, body: str) -> None:
        name = (title or "").strip() or "NOTE"
        self._title.setText(name)
        self._path.setText(path or "")
        self._path.setVisible(bool(path))
        raw = (body or "").strip()
        if not raw:
            self._body.setHtml("<p style='opacity:0.6'>(내용 없음)</p>")
            return
        html = markdown_to_chat_html(raw)
        self._body.setHtml(html or "<p style='opacity:0.6'>(내용 없음)</p>")

    def clear(self) -> None:
        self._title.setText("NOTE")
        self._path.clear()
        self._path.hide()
        self._body.clear()
