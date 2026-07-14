"""ParticleVisualizer — 컴팩트 영역에서 구체 외곽이 잘리지 않는지."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.ui.particle_visualizer import ParticleVisualizer, _EDGE_PAD, _VISUAL_HALO_FACTOR


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_compact_orb_stays_inside_widget_bounds(qapp) -> None:
    """Assistant Dock 크기에서 구체 외곽이 위·아래로 잘리지 않아야 한다."""
    viz = ParticleVisualizer()
    viz.set_size_scale(1.65)
    viz.resize(320, 264)
    viz.show()
    qapp.processEvents()
    cx, cy = viz.effective_center()
    halo = viz._core_r * _VISUAL_HALO_FACTOR  # noqa: SLF001
    assert cy - halo >= _EDGE_PAD - 0.5
    assert cy + halo <= viz.height() - _EDGE_PAD + 0.5
    assert abs(cx - viz.width() * 0.5) < 0.5
