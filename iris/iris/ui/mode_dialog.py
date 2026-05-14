"""모드 선택 다이얼로그 (선택)."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QVBoxLayout


class ModeDialog(QDialog):
    """간단 프리셋 선택."""

    def __init__(self, titles: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("모드 선택")
        self._list = QListWidget()
        for t in titles:
            self._list.addItem(t)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self._list)
        lay.addWidget(buttons)

    def selected_text(self) -> str:
        item = self._list.currentItem()
        return item.text() if item else ""
