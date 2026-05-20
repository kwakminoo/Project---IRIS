"""설정 창 — 앱 런처 인덱스 목록·수동 추가·감지 스캔."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iris.config.app_index import is_runnable_exe, slug_app_key
from iris.storage.database import Database
from iris.ui.workers import AppLauncherScanWorker


class AppLauncherPanel(QWidget):
    """앱 런처 DB 목록 + 수동 추가 + 「앱 런처 감지」."""

    def __init__(
        self,
        db: Database,
        *,
        on_paths_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._on_paths_changed = on_paths_changed
        self._scan_worker: AppLauncherScanWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("앱 런처")
        box_layout = QVBoxLayout(box)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["표시명", "app_key", "경로", "출처"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        box_layout.addWidget(self._table)

        form = QFormLayout()
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("예: notepad (비우면 표시명에서 자동)")
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("예: 메모장")
        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText(r"예: C:\Windows\System32\notepad.exe")
        form.addRow("app_key", self._key_input)
        form.addRow("표시명", self._name_input)
        form.addRow("exe 경로", self._path_input)
        box_layout.addLayout(form)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("추가")
        self._btn_detect = QPushButton("앱 런처 감지")
        self._btn_delete = QPushButton("삭제")
        self._btn_add.clicked.connect(self._on_add_manual)
        self._btn_detect.clicked.connect(self._on_detect)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_detect)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch(1)
        box_layout.addLayout(btn_row)

        help_lbl = QLabel(
            "PC에 설치된 앱을 시작 메뉴·App Paths에서 찾아 등록합니다. "
            "새 앱 설치 시 시작 메뉴 shortcut이 생기면 자동으로 추가됩니다."
        )
        help_lbl.setWordWrap(True)
        box_layout.addWidget(help_lbl)

        root.addWidget(box)
        self.reload_table()

    def reload_table(self) -> None:
        rows = self._db.list_app_launcher_entries()
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(str(row["display_name"])))
            self._table.setItem(i, 1, QTableWidgetItem(str(row["app_key"])))
            self._table.setItem(i, 2, QTableWidgetItem(str(row["exe_path"])))
            self._table.setItem(i, 3, QTableWidgetItem(str(row["source"])))

    @pyqtSlot()
    def _on_add_manual(self) -> None:
        disp = self._name_input.text().strip()
        path = self._path_input.text().strip()
        key = self._key_input.text().strip() or (slug_app_key(disp) if disp else "")
        if not key or not disp or not path:
            QMessageBox.warning(self, "앱 런처", "app_key, 표시명, exe 경로를 모두 입력하세요.")
            return
        if not is_runnable_exe(path):
            QMessageBox.warning(self, "앱 런처", "실행 파일을 찾을 수 없거나 유효하지 않습니다.")
            return
        self._db.upsert_app_launcher_entry(key, disp, path, "manual")
        self._key_input.clear()
        self._name_input.clear()
        self._path_input.clear()
        self.reload_table()
        if self._on_paths_changed:
            self._on_paths_changed()

    @pyqtSlot()
    def _on_delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        key_item = self._table.item(row, 1)
        if not key_item:
            return
        key = key_item.text()
        if QMessageBox.question(
            self,
            "앱 런처",
            f"'{key}' 항목을 삭제할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_app_launcher_entry(key)
        self.reload_table()
        if self._on_paths_changed:
            self._on_paths_changed()

    @pyqtSlot()
    def _on_detect(self) -> None:
        if self._scan_worker and self._scan_worker.isRunning():
            return
        self._btn_detect.setEnabled(False)
        self._scan_worker = AppLauncherScanWorker(self._db, parent=self)
        self._scan_worker.finished_scan.connect(self._on_scan_finished)
        self._scan_worker.start()

    @pyqtSlot(int, list)
    def _on_scan_finished(self, new_count: int, names: list) -> None:
        self._btn_detect.setEnabled(True)
        self.reload_table()
        if self._on_paths_changed:
            self._on_paths_changed()
        if new_count <= 0:
            QMessageBox.information(self, "앱 런처", "변동사항이 없습니다.")
            return
        shown = names[:5]
        extra = new_count - len(shown)
        body = ", ".join(shown)
        if extra > 0:
            body = f"{body} 외 {extra}개"
        QMessageBox.information(
            self,
            "앱 런처",
            f"{new_count}개 앱을 추가했습니다: {body}",
        )
