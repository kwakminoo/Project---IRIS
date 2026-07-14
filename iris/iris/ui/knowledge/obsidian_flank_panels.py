"""Obsidian 플랭크 패널 — Iris 중앙 양옆 지식 노트."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.ui.theme_tokens import TOKENS


@dataclass(frozen=True)
class ObsidianNoteItem:
    """UI 목록용 노트 요약."""

    source_id: int
    title: str
    path: str
    status: str
    preview: str


class ObsidianNoteListPanel(QWidget):
    """좌측 — 인덱싱된 소스·노트 목록."""

    note_selected = pyqtSignal(int)  # source_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianNoteListPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(260)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 4, 8)
        lay.setSpacing(6)
        title = QLabel("Iris Wiki")
        title.setObjectName("ObsidianPanelTitle")
        title.setStyleSheet(f"color: {TOKENS.neon_purple}; font-weight: 600;")
        lay.addWidget(title)
        self._list = QListWidget()
        self._list.setObjectName("ObsidianNoteList")
        self._list.currentRowChanged.connect(self._on_row_changed)
        lay.addWidget(self._list, 1)
        self._items: list[ObsidianNoteItem] = []

    def set_notes(self, notes: list[ObsidianNoteItem]) -> None:
        self._items = list(notes)
        self._list.clear()
        for note in notes:
            label = note.title or note.path.rsplit("\\", 1)[-1]
            item = QListWidgetItem(f"{label}\n{note.status}")
            item.setData(Qt.ItemDataRole.UserRole, note.source_id)
            item.setToolTip(note.path)
            self._list.addItem(item)

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._items):
            return
        self.note_selected.emit(self._items[row].source_id)


class ObsidianPreviewPanel(QWidget):
    """우측 — 선택 노트 미리보기."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianPreviewPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 6, 8)
        lay.setSpacing(6)
        self._title = QLabel("미리보기")
        self._title.setObjectName("ObsidianPanelTitle")
        self._title.setStyleSheet(f"color: {TOKENS.neon_purple}; font-weight: 600;")
        lay.addWidget(self._title)
        self._body = QPlainTextEdit()
        self._body.setObjectName("ObsidianPreviewBody")
        self._body.setReadOnly(True)
        lay.addWidget(self._body, 1)

    def show_note(self, *, title: str, path: str, body: str) -> None:
        self._title.setText(title or "미리보기")
        header = f"{path}\n\n" if path else ""
        self._body.setPlainText(header + (body or "(내용 없음)"))

    def clear_preview(self) -> None:
        self._body.clear()
