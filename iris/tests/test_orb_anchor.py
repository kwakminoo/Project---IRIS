"""Orb anchor 동기화 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from iris.ui.cyberspace_background import CyberspaceBackground
from iris.ui.visualizer import Visualizer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_orb_fixture(qapp) -> tuple[CyberspaceBackground, Visualizer, QWidget]:
    bg = CyberspaceBackground()
    viz = Visualizer(bg)
    bg.set_orb_layer(viz)
    overlay = QWidget()
    bg.set_ui_overlay(overlay)
    lay = QVBoxLayout(overlay)
    anchor = QWidget()
    anchor.setMinimumHeight(160)
    lay.addWidget(anchor, 2)
    lay.addStretch(3)
    bg.resize(960, 640)
    bg.show()
    viz.set_orb_anchor(anchor)
    qapp.processEvents()
    return bg, viz, anchor


def test_orb_anchor_within_2px(qapp) -> None:
    bg, viz, _anchor = _build_orb_fixture(qapp)
    offset = viz.orb_center_offset()
    assert offset is not None
    assert abs(offset[0]) <= 2.0
    assert abs(offset[1]) <= 2.0
    bg.close()


def test_orb_anchor_after_resize(qapp) -> None:
    bg, viz, _anchor = _build_orb_fixture(qapp)
    for size in ((1280, 720), (1920, 1080), (960, 640)):
        bg.resize(*size)
        for _ in range(4):
            qapp.processEvents()
        viz.request_sync_orb_anchor()
        for _ in range(2):
            qapp.processEvents()
        offset = viz.orb_center_offset()
        assert offset is not None
        assert abs(offset[0]) <= 2.0
        assert abs(offset[1]) <= 2.0
    bg.close()


def test_orb_anchor_after_maximize_restore(qapp) -> None:
    bg, viz, _anchor = _build_orb_fixture(qapp)
    for _ in range(3):
        bg.showMaximized()
        qapp.processEvents()
        viz.request_sync_orb_anchor()
        qapp.processEvents()
        offset = viz.orb_center_offset()
        assert offset is not None
        assert abs(offset[0]) <= 2.0
        assert abs(offset[1]) <= 2.0
        bg.showNormal()
        qapp.processEvents()
        viz.request_sync_orb_anchor()
        qapp.processEvents()
        offset = viz.orb_center_offset()
        assert offset is not None
        assert abs(offset[0]) <= 2.0
        assert abs(offset[1]) <= 2.0
    bg.close()
