"""Coding Panel 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.core.state_machine import AppState
from iris.ui.ide.iris_assistant_dock import IrisAssistantDock


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_coding_panel_contains_orb(qapp) -> None:
    panel = IrisAssistantDock()
    assert panel.orb is not None


def test_coding_panel_contains_chat_history(qapp) -> None:
    panel = IrisAssistantDock()
    assert panel.chat is not None
    assert panel.chat._log is not None


def test_coding_panel_contains_text_input(qapp) -> None:
    panel = IrisAssistantDock()
    assert panel.chat._input is not None
    assert panel.chat._send_btn is not None


def test_coding_panel_has_no_voice_button(qapp) -> None:
    panel = IrisAssistantDock()
    assert not hasattr(panel.chat, "_mic_btn")


def test_coding_panel_contains_waveform(qapp) -> None:
    panel = IrisAssistantDock()
    assert panel.wave is not None


def test_coding_panel_has_three_main_sections(qapp) -> None:
    panel = IrisAssistantDock()
    assert panel.orb is not None
    assert panel.chat is not None
    assert panel.wave is not None
    assert not hasattr(panel, "live_activity")


def test_coding_panel_workspace_label_between_orb_and_chat(qapp) -> None:
    panel = IrisAssistantDock()
    panel.set_workspace_label("IRIS / demo")
    assert panel._workspace_label.text() == "IRIS / demo"
    layout = panel.layout()
    orb_idx = layout.indexOf(panel.orb)
    label_idx = layout.indexOf(panel._workspace_label)
    chat_idx = layout.indexOf(panel.chat)
    assert orb_idx < label_idx < chat_idx


def test_orb_state_changes_with_assistant_state(qapp) -> None:
    panel = IrisAssistantDock()
    panel.set_app_state(AppState.LISTENING)
    assert panel.orb.particle_core()._state_name == "LISTENING"
