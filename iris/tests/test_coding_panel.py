"""Coding Panel 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.core.state_machine import AppState
from iris.ui.ide.iris_coding_panel import IrisCodingPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_coding_panel_contains_orb(qapp) -> None:
    panel = IrisCodingPanel()
    assert panel.orb is not None


def test_coding_panel_contains_chat_history(qapp) -> None:
    panel = IrisCodingPanel()
    assert panel.chat is not None
    assert panel.chat._log is not None


def test_coding_panel_contains_text_input(qapp) -> None:
    panel = IrisCodingPanel()
    assert panel.chat._input is not None
    assert panel.chat._send_btn is not None


def test_coding_panel_has_no_voice_button(qapp) -> None:
    panel = IrisCodingPanel()
    assert not hasattr(panel.chat, "_mic_btn")


def test_orb_state_changes_with_assistant_state(qapp) -> None:
    panel = IrisCodingPanel()
    panel.set_app_state(AppState.LISTENING)
    assert panel.orb.particle_core()._state_name == "LISTENING"
