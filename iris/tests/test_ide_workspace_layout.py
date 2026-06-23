"""IDE Workspace 레이아웃·editor 상태 전환 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.infrastructure.ide.ide_bridge_client import IdeBridgeClient, IdeEditorState
from iris.ui.workspaces.ide_workspace_page import IdeWorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_editor_state_from_payload() -> None:
    state = IdeEditorState.from_payload({
        "type": "iris.ide.editorStateChanged",
        "hasOpenEditor": True,
        "title": "app.py",
        "uri": "file:///tmp/app.py",
        "languageId": "python",
    })
    assert state.has_open_editor is True
    assert state.title == "app.py"
    assert state.language_id == "python"


def test_bridge_editor_state_http(qapp) -> None:
    client = IdeBridgeClient()
    received: list[tuple[bool, str, str, str]] = []

    def _cb(has_open: bool, title: str, uri: str, lang: str) -> None:
        received.append((has_open, title, uri, lang))

    client.set_editor_state_callback(_cb)
    client.start()
    try:
        client._apply_editor_state({
            "type": "iris.ide.editorStateChanged",
            "hasOpenEditor": True,
            "title": "main.py",
            "uri": "file:///ws/main.py",
            "languageId": "python",
        })
        assert received[-1][0] is True
        assert received[-1][1] == "main.py"
        client._apply_editor_state({
            "type": "iris.ide.editorStateChanged",
            "hasOpenEditor": False,
            "title": "",
            "uri": "",
            "languageId": "",
        })
        assert received[-1] == (False, "", "", "")
    finally:
        client.stop()


def test_ide_page_empty_home_visible_by_default(qapp) -> None:
    page = IdeWorkspacePage()
    page.resize(1280, 800)
    page.show()
    qapp.processEvents()
    assert page.empty_home.isVisible()
    assert page.coding_panel.isVisible()
    assert page.iris_orb.parent() is page.empty_home._orb_slot


def test_ide_page_editor_state_switches_layout(qapp) -> None:
    page = IdeWorkspacePage()
    page.resize(1600, 900)
    page.show()
    qapp.processEvents()
    page.set_editor_state(True, title="foo.ts", language_id="typescript")
    qapp.processEvents()
    assert page.has_open_editor is True
    assert not page.empty_home.isVisible()
    assert page.coding_panel.isVisible()
    assert page.coding_panel.orb is page.iris_orb

    page.set_editor_state(False)
    qapp.processEvents()
    assert not page.has_open_editor
    assert not page.empty_home.isVisible()
    assert page.coding_panel.orb is page.iris_orb

    page.show_empty_home()
    qapp.processEvents()
    assert page.empty_home.isVisible()
    assert page.iris_orb.parent() is page.empty_home._orb_slot


def test_ide_page_active_chat_uses_assistant_dock(qapp) -> None:
    page = IdeWorkspacePage()
    page.set_editor_state(False)
    assert page.active_chat() is page.coding_panel.chat
    page.set_editor_state(True, title="a.py")
    assert page.active_chat() is page.coding_panel.chat
