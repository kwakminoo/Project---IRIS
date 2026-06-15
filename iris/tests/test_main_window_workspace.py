"""Workspace 전환·Persistent Sidebar 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QStackedWidget

from iris.ui.left_sidebar_panel import LeftSidebarPanel
from iris.ui.workspaces.assistant_workspace_page import AssistantWorkspacePage
from iris.ui.workspaces.ide_workspace_page import IdeWorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_workspace_stack_contains_assistant_and_ide_pages(qapp) -> None:
    stack = QStackedWidget()
    assistant = AssistantWorkspacePage()
    ide = IdeWorkspacePage()
    stack.addWidget(assistant)
    stack.addWidget(ide)
    assert stack.count() == 2
    assert isinstance(stack.widget(0), AssistantWorkspacePage)
    assert isinstance(stack.widget(1), IdeWorkspacePage)


def test_left_sidebar_contains_window_list_and_metrics(qapp) -> None:
    sidebar = LeftSidebarPanel()
    assert sidebar.window_list is not None
    assert sidebar.utility.metrics is not None
    assert sidebar.utility.actions is not None


def test_assistant_page_preserves_splitter_state(qapp) -> None:
    page = AssistantWorkspacePage()
    before = page.save_splitter_state()
    page.restore_splitter_state(before)
    assert page.save_splitter_state() == before


def test_ide_page_has_theia_and_coding_panel(qapp) -> None:
    page = IdeWorkspacePage()
    assert page.theia is not None
    assert page.coding_panel is not None
