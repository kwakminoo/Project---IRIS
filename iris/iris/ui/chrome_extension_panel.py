"""설정창 — Chrome 확장 연결 상태·동기화."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QTimer, Qt, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.config.settings import Settings
from iris.monitoring.browser_tab_monitor import BrowserTabMonitor
from iris.monitoring.extension_setup import launch_chrome_extension_setup
from iris.monitoring.extension_status import (
    ChromeExtensionStatus,
    ExtensionLinkLevel,
    evaluate_extension_status,
)


class ChromeExtensionPanel(QWidget):
    """Chrome 확장 설치·연결 상태."""

    def __init__(
        self,
        settings: Settings,
        browser: BrowserTabMonitor,
        *,
        server_active: Callable[[], bool],
        ensure_server: Callable[[], bool],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._browser = browser
        self._server_active = server_active
        self._ensure_server = ensure_server

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel("Chrome 확장 (Iris Tab Monitor)")
        header.setObjectName("PanelSubtitle")
        layout.addWidget(header)

        self._status_label = QLabel("상태 확인 중…")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet("color: #a8b0c8; font-size: 12px;")
        layout.addWidget(self._detail_label)

        row = QHBoxLayout()
        self._btn_refresh = QPushButton("연결 확인")
        self._btn_sync = QPushButton("Chrome 확장 동기화")
        self._btn_refresh.clicked.connect(self.refresh_status)
        self._btn_sync.clicked.connect(self._on_sync_clicked)
        row.addWidget(self._btn_refresh)
        row.addWidget(self._btn_sync, 1)
        layout.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self.refresh_status)

    def start_polling(self) -> None:
        self.refresh_status()
        self._timer.start()

    def stop_polling(self) -> None:
        self._timer.stop()

    @pyqtSlot()
    def refresh_status(self) -> None:
        self._ensure_server()
        st = evaluate_extension_status(
            self._settings,
            self._browser,
            server_active=self._server_active(),
        )
        self._apply_status_style(st)
        self._status_label.setText(st.summary)
        self._detail_label.setText(st.detail)
        need_sync = st.level != ExtensionLinkLevel.CONNECTED
        self._btn_sync.setEnabled(True)
        self._btn_sync.setText(
            "Chrome 확장 동기화" if need_sync else "확장 설정 다시 열기"
        )

    def _apply_status_style(self, st: ChromeExtensionStatus) -> None:
        color = {
            ExtensionLinkLevel.CONNECTED: "#5dca8a",
            ExtensionLinkLevel.WAITING_EXTENSION: "#e6b84d",
            ExtensionLinkLevel.SERVER_DOWN: "#e07070",
        }.get(st.level, "#c8ccd8")
        self._status_label.setStyleSheet(
            f"color: {color}; font-weight: 600; font-size: 13px;"
        )

    @pyqtSlot()
    def _on_sync_clicked(self) -> None:
        self._ensure_server()
        result = launch_chrome_extension_setup()
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(str(result.extension_dir))

        if not result.ok:
            QMessageBox.warning(self, "Chrome 확장", result.message)
            return

        QMessageBox.information(
            self,
            "Chrome 확장 동기화",
            result.message
            + "\n\n확장 폴더 경로가 클립보드에 복사되었습니다.",
        )
        self.refresh_status()
