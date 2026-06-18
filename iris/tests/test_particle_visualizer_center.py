"""ParticleVisualizer custom center → effective center 즉시 반영 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from iris.ui.particle_visualizer import ParticleVisualizer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_set_custom_center_immediate_reflect(qapp) -> None:
    """resizeEvent 없이 set_custom_center 직후 effective_center가 일치해야 한다."""
    viz = ParticleVisualizer()
    viz.resize(1280, 800)
    viz.set_custom_center(500, 250)
    assert viz.effective_center() == (500.0, 250.0)
    assert viz.custom_center() == (500.0, 250.0)


def test_set_custom_center_consecutive_changes(qapp) -> None:
    """연속 center 변경 시 마지막 값이 즉시 effective에 반영되어야 한다."""
    viz = ParticleVisualizer()
    viz.resize(1280, 800)
    viz.set_custom_center(500, 250)
    viz.set_custom_center(780, 280)
    assert viz.effective_center() == (780.0, 280.0)


def test_maximize_restore_sequence_simulation(qapp) -> None:
    """최대화·복원 순서 모사 — 마지막 center가 resize 없이도 유지."""
    viz = ParticleVisualizer()
    viz.resize(1280, 800)

    normal_center = (640.0, 270.0)
    viz.set_custom_center(*normal_center)
    viz.resize(1280, 800)

    maximized_center = (960.0, 400.0)
    viz.set_custom_center(*maximized_center)
    viz.resize(1920, 1080)

    viz.set_custom_center(*normal_center)
    assert viz.effective_center() == normal_center
    assert viz.custom_center() == normal_center


def test_target_and_effective_always_match_after_set(qapp) -> None:
    """set_custom_center 직후 target과 effective가 항상 일치해야 한다."""
    viz = ParticleVisualizer()
    viz.resize(1280, 800)
    viz.set_custom_center(500, 250)
    target = viz.custom_center()
    effective = viz.effective_center()
    assert target is not None
    assert effective[0] == target[0]
    assert effective[1] == target[1]
