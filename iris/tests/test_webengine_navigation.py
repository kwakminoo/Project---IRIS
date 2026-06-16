"""WebEngine 내비게이션 정책 테스트."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

from iris.ui.ide.iris_webengine_page import IrisWebEnginePage

_app = QApplication.instance() or QApplication(sys.argv)


def test_blocks_javascript_scheme() -> None:
    page = IrisWebEnginePage()
    assert page._is_navigation_allowed(QUrl("javascript:alert(1)")) is False


def test_blocks_file_scheme() -> None:
    page = IrisWebEnginePage()
    assert page._is_navigation_allowed(QUrl("file:///C:/secret")) is False


def test_allows_localhost_ide() -> None:
    page = IrisWebEnginePage(ide_port_callback=lambda: 3100)
    assert page._is_navigation_allowed(QUrl("http://127.0.0.1:3100/")) is True


def test_blocks_wrong_port() -> None:
    page = IrisWebEnginePage(ide_port_callback=lambda: 3100)
    assert page._is_navigation_allowed(QUrl("http://127.0.0.1:3199/")) is False
