"""설정 창 — 외부 API·MCP 연동 등록."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from iris.storage.database import Database


class IntegrationsPanel(QWidget):
    """API·MCP 엔드포인트 CRUD + 연결 테스트."""

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("API · MCP 연동")
        lay = QVBoxLayout(box)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["이름", "종류", "URL", "명령(MCP)", "활성"]
        )
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        lay.addWidget(self._table)

        form = QFormLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("예: discord_bot, my_api")
        self._kind_combo = QComboBox()
        self._kind_combo.addItem("REST API", "api")
        self._kind_combo.addItem("MCP 서버", "mcp")
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://api.example.com 또는 http://localhost:3000/mcp")
        self._cmd_input = QLineEdit()
        self._cmd_input.setPlaceholderText("MCP stdio: npx -y @modelcontextprotocol/server-filesystem C:\\")
        self._auth_input = QLineEdit()
        self._auth_input.setPlaceholderText("선택: Bearer TOKEN 또는 X-API-Key: value")
        self._notes_input = QLineEdit()
        self._enabled_check = QCheckBox("활성")
        self._enabled_check.setChecked(True)
        form.addRow("이름", self._name_input)
        form.addRow("종류", self._kind_combo)
        form.addRow("Base URL", self._url_input)
        form.addRow("MCP 명령", self._cmd_input)
        form.addRow("인증 헤더", self._auth_input)
        form.addRow("메모", self._notes_input)
        form.addRow("", self._enabled_check)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("저장")
        self._btn_test = QPushButton("연결 테스트")
        self._btn_delete = QPushButton("삭제")
        self._btn_save.clicked.connect(self._on_save)
        self._btn_test.clicked.connect(self._on_test)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_test)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        help_lbl = QLabel(
            "REST API: Base URL + action 경로로 POST/GET 합니다. "
            "MCP: HTTP URL 또는 stdio 명령(npx 등)으로 tools/call을 호출합니다. "
            "Computer Use 플래너는 call_integration 도구로 등록된 연동을 우선 사용합니다."
        )
        help_lbl.setWordWrap(True)
        lay.addWidget(help_lbl)

        root.addWidget(box)
        self.reload_table()

    def reload_table(self) -> None:
        rows = self._db.list_integration_endpoints()
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(str(row["name"])))
            self._table.setItem(i, 1, QTableWidgetItem(str(row["kind"])))
            self._table.setItem(i, 2, QTableWidgetItem(str(row["base_url"])))
            self._table.setItem(i, 3, QTableWidgetItem(str(row["command"])))
            enabled = "예" if int(row["enabled"]) else "아니오"
            self._table.setItem(i, 4, QTableWidgetItem(enabled))

    @pyqtSlot()
    def _on_row_selected(self) -> None:
        items = self._table.selectedItems()
        if not items:
            return
        row_idx = items[0].row()
        name_item = self._table.item(row_idx, 0)
        if name_item is None:
            return
        rec = self._db.get_integration_endpoint(name_item.text())
        if rec is None:
            return
        self._name_input.setText(str(rec["name"]))
        kind = str(rec["kind"]).lower()
        idx = self._kind_combo.findData(kind)
        if idx >= 0:
            self._kind_combo.setCurrentIndex(idx)
        self._url_input.setText(str(rec["base_url"]))
        self._cmd_input.setText(str(rec["command"]))
        self._auth_input.setText(str(rec["auth_header"]))
        self._notes_input.setText(str(rec["notes"]))
        self._enabled_check.setChecked(bool(int(rec["enabled"])))

    @pyqtSlot()
    def _on_save(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "연동", "이름을 입력하세요.")
            return
        kind = str(self._kind_combo.currentData() or "api")
        url = self._url_input.text().strip()
        cmd = self._cmd_input.text().strip()
        if kind == "api" and not url:
            QMessageBox.warning(self, "연동", "API는 Base URL이 필요합니다.")
            return
        if kind == "mcp" and not url and not cmd:
            QMessageBox.warning(self, "연동", "MCP는 URL 또는 stdio 명령이 필요합니다.")
            return
        self._db.upsert_integration_endpoint(
            name,
            kind=kind,
            base_url=url,
            command=cmd,
            auth_header=self._auth_input.text().strip(),
            enabled=self._enabled_check.isChecked(),
            notes=self._notes_input.text().strip(),
        )
        self.reload_table()
        QMessageBox.information(self, "연동", f"'{name}' 연동을 저장했습니다.")

    @pyqtSlot()
    def _on_test(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "연동", "테스트할 이름을 입력하거나 목록에서 선택하세요.")
            return
        row = self._db.get_integration_endpoint(name)
        if row is None:
            self._on_save()
        ok, msg = self._db.test_integration_endpoint(name)
        if ok:
            QMessageBox.information(self, "연결 테스트", msg)
        else:
            QMessageBox.warning(self, "연결 테스트", msg)

    @pyqtSlot()
    def _on_delete(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            return
        if not self._db.delete_integration_endpoint(name):
            QMessageBox.warning(self, "연동", "삭제할 항목이 없습니다.")
            return
        self._name_input.clear()
        self._url_input.clear()
        self._cmd_input.clear()
        self.reload_table()
