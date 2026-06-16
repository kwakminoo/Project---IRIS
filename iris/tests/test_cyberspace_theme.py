"""사이버스페이스 테마·orb 렌더링 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.ui.cyberspace_background import CyberspaceBackground
from iris.ui.cyberspace_theme import build_cyberspace_qss
from iris.ui.particle_visualizer import ParticleVisualizer, _STATE_PROFILES
from iris.ui.theme_tokens import TOKENS
from iris.ui.workspace_action_panel import WorkspaceActionPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_theme_tokens_cyberspace_palette(qapp) -> None:
    assert TOKENS.void_black == "#020408"
    assert TOKENS.neon_blue == "#38bdf8"
    assert TOKENS.metric_fill_cpu == "#3b82f6"


def test_cyberspace_qss_contains_hud_selectors(qapp) -> None:
    qss = build_cyberspace_qss()
    assert "HudMetricBar" in qss
    assert "HudModeButton" in qss
    assert "HudWindowRow" in qss
    assert TOKENS.neon_blue in qss or TOKENS.text_primary in qss


def test_cyberspace_background_instantiates(qapp) -> None:
    bg = CyberspaceBackground()
    bg.resize(400, 300)
    bg.show()
    qapp.processEvents()
    assert bg.width() == 400


@pytest.mark.parametrize(
    "state",
    ["IDLE", "LISTENING", "PROCESSING", "EXECUTING", "RESPONDING", "ERROR"],
)
def test_particle_visualizer_state_profiles(qapp, state: str) -> None:
    assert state in _STATE_PROFILES
    viz = ParticleVisualizer()
    viz.resize(320, 240)
    viz.set_state(state)
    viz.show()
    qapp.processEvents()
    assert viz._state_name == state  # noqa: SLF001


def test_particle_visualizer_paints_without_crash(qapp) -> None:
    viz = ParticleVisualizer()
    viz.resize(400, 300)
    viz.set_state("LISTENING")
    viz.show()
    for _ in range(3):
        viz._tick()  # noqa: SLF001
    qapp.processEvents()


def test_workspace_action_panel_hud_button(qapp) -> None:
    panel = WorkspaceActionPanel()
    fired: list[str] = []

    panel.add_action(
        action_id="test",
        title="Test",
        tooltip="t",
        callback=lambda: fired.append("ok"),
    )
    panel.set_action_active("test", True)
    btn = panel._buttons["test"]  # noqa: SLF001
    assert btn.property("active") is True
    btn.click()
    assert fired == ["ok"]
