"""IDE Shell 레이아웃 분리·겹침 방지 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.ui.ide.ide_layout_constants import (
  ASSISTANT_DOCK_ORB_HEIGHT,
  THEIA_MENU_BAR_HEIGHT,
  THEIA_STATUS_BAR_HEIGHT,
)
from iris.ui.ide.ide_shell_layout import IdeShellLayout
from iris.ui.ide.iris_assistant_dock import IrisAssistantDock
from iris.ui.workspaces.ide_workspace_page import IdeWorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ide_shell_horizontal_split_no_overlap(qapp) -> None:
    shell = IdeShellLayout()
    shell.resize(1280, 800)
    shell.show()
    qapp.processEvents()

    theia_right = shell.theia_host.geometry().right()
    dock_left = shell.assistant_dock.geometry().left()
    assert theia_right <= dock_left


def test_assistant_dock_uses_chrome_margins(qapp) -> None:
    dock = IrisAssistantDock()
    margins = dock.layout().contentsMargins()
    assert margins.top() == THEIA_MENU_BAR_HEIGHT
    assert margins.bottom() == THEIA_STATUS_BAR_HEIGHT


def test_assistant_dock_sections_in_single_layout(qapp) -> None:
    dock = IrisAssistantDock()
    layout = dock.layout()
    orb_idx = layout.indexOf(dock._orb_slot)
    label_idx = layout.indexOf(dock._workspace_label)
    chat_idx = layout.indexOf(dock.chat)
    wave_idx = layout.indexOf(dock.wave)
    assert orb_idx < label_idx < chat_idx < wave_idx


def test_orb_fixed_height_in_assistant_dock(qapp) -> None:
    from iris.ui.ide.iris_orb_widget import IrisOrbWidget

    dock = IrisAssistantDock()
    orb = IrisOrbWidget()
    dock.mount_orb(orb)
    assert orb.height() == ASSISTANT_DOCK_ORB_HEIGHT
    dock.resize(320, 400)
    qapp.processEvents()
    assert orb.height() == ASSISTANT_DOCK_ORB_HEIGHT


def test_center_orb_hidden_in_editor_mode(qapp) -> None:
    page = IdeWorkspacePage()
    page.resize(1280, 800)
    page.show()
    qapp.processEvents()
    page.set_editor_state(True, title="main.py")
    qapp.processEvents()
    assert not page.empty_home.isVisible()
    assert page.coding_panel.isVisible()


def test_center_orb_visible_in_empty_home(qapp) -> None:
    page = IdeWorkspacePage()
    page.resize(1280, 800)
    page.show()
    qapp.processEvents()
    assert page.empty_home.isVisible()
    assert page.coding_panel.isVisible()
