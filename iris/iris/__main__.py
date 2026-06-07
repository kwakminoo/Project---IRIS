"""python -m iris 진입점."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from iris.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Iris")
    app.setFont(QFont("Noto Sans KR", 10))
    win = MainWindow()
    win.show()
    # 창을 먼저 그린 뒤 deferred_startup_services(QTimer)가 돌도록 한 틱 양보
    app.processEvents()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
