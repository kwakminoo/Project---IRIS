"""python -m iris 진입점."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from iris.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Iris")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
