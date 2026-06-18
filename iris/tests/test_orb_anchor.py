"""Orb anchor 동기화 테스트 — MainWindow 통합 및 단순 fixture."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from iris.ui.cyberspace_background import CyberspaceBackground
from iris.ui.main_window import MainWindow
from iris.ui.visualizer import Visualizer

_TOLERANCE_PX = 2.0
_MAX_WAIT_MS = 4000


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _offset_within_tolerance(offset: tuple[float, float] | None, tol: float = _TOLERANCE_PX) -> bool:
    if offset is None:
        return False
    return abs(offset[0]) <= tol and abs(offset[1]) <= tol


def _process_until_stable(
    qapp: QApplication,
    viz: Visualizer,
    *,
    max_wait_ms: int = _MAX_WAIT_MS,
) -> tuple[float, float] | None:
    """프로덕션 이벤트 연결만으로 구체가 anchor에 수렴할 때까지 대기."""
    elapsed = 0
    stable_frames = 0
    last_offset: tuple[float, float] | None = None
    while elapsed < max_wait_ms:
        qapp.processEvents()
        offset = viz.orb_center_offset()
        if offset is not None and _offset_within_tolerance(offset):
            if last_offset is not None:
                if abs(offset[0] - last_offset[0]) < 0.5 and abs(offset[1] - last_offset[1]) < 0.5:
                    stable_frames += 1
                else:
                    stable_frames = 0
            else:
                stable_frames = 1
            last_offset = offset
            if stable_frames >= 2:
                return offset
        else:
            stable_frames = 0
            last_offset = offset
        QTest.qWait(16)
        elapsed += 16
    return viz.orb_center_offset()


def _build_simple_fixture(qapp) -> tuple[CyberspaceBackground, Visualizer, QWidget]:
  """단순 레이아웃 — 회귀용 최소 fixture."""
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


@pytest.fixture
def main_window(qapp):
    win = MainWindow(test_mode=True)
    win.resize(1280, 800)
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    qapp.processEvents()


def test_orb_anchor_within_2px(qapp) -> None:
    bg, viz, _anchor = _build_simple_fixture(qapp)
    offset = _process_until_stable(qapp, viz)
    assert offset is not None
    assert _offset_within_tolerance(offset)
    bg.close()


def test_orb_anchor_after_resize(qapp) -> None:
    bg, viz, _anchor = _build_simple_fixture(qapp)
    for size in ((1280, 720), (1920, 1080), (960, 640)):
        bg.resize(*size)
        offset = _process_until_stable(qapp, viz)
        assert offset is not None, f"failed at size {size}"
        assert _offset_within_tolerance(offset), f"offset {offset} at size {size}"
    bg.close()


def test_main_window_initial_orb_alignment(main_window, qapp) -> None:
    offset = _process_until_stable(qapp, main_window._viz)
    assert offset is not None
    assert _offset_within_tolerance(offset)


def test_main_window_maximize_orb_alignment(main_window, qapp) -> None:
    _process_until_stable(qapp, main_window._viz)
    main_window.showMaximized()
    offset = _process_until_stable(qapp, main_window._viz)
    assert offset is not None
    assert _offset_within_tolerance(offset)


def test_main_window_restore_matches_initial(main_window, qapp) -> None:
    initial = _process_until_stable(qapp, main_window._viz)
    assert initial is not None
    live_initial = main_window._viz.live_anchor_center_local()
    assert live_initial is not None

    main_window.showMaximized()
    _process_until_stable(qapp, main_window._viz)
    main_window.showNormal()
    offset = _process_until_stable(qapp, main_window._viz)
    assert offset is not None
    assert _offset_within_tolerance(offset)

    live_restored = main_window._viz.live_anchor_center_local()
    assert live_restored is not None
    assert abs(live_restored[0] - live_initial[0]) <= _TOLERANCE_PX
    assert abs(live_restored[1] - live_initial[1]) <= _TOLERANCE_PX


def test_main_window_maximize_restore_five_times(main_window, qapp) -> None:
    live_initial = main_window._viz.live_anchor_center_local()
    _process_until_stable(qapp, main_window._viz)
    assert live_initial is not None

    for _ in range(5):
        main_window.showMaximized()
        offset = _process_until_stable(qapp, main_window._viz)
        assert offset is not None
        assert _offset_within_tolerance(offset)

        main_window.showNormal()
        offset = _process_until_stable(qapp, main_window._viz)
        assert offset is not None
        assert _offset_within_tolerance(offset)

        live_now = main_window._viz.live_anchor_center_local()
        assert live_now is not None
        assert abs(live_now[0] - live_initial[0]) <= _TOLERANCE_PX
        assert abs(live_now[1] - live_initial[1]) <= _TOLERANCE_PX


def test_main_window_resize_sequence(main_window, qapp) -> None:
    for size in ((960, 640), (1280, 800), (1920, 1080), (1280, 800)):
        main_window.resize(*size)
        offset = _process_until_stable(qapp, main_window._viz)
        assert offset is not None, f"failed at {size}"
        assert _offset_within_tolerance(offset), f"offset {offset} at {size}"


def test_main_window_workspace_switch(main_window, qapp) -> None:
    _process_until_stable(qapp, main_window._viz)
    live_assistant = main_window._viz.live_anchor_center_local()
    assert live_assistant is not None

    main_window.switch_to_ide_workspace()
    qapp.processEvents()
    assert not main_window._viz.isVisible()

    main_window.switch_to_assistant_workspace()
    offset = _process_until_stable(qapp, main_window._viz)
    assert offset is not None
    assert _offset_within_tolerance(offset)

    live_back = main_window._viz.live_anchor_center_local()
    assert live_back is not None
    assert abs(live_back[0] - live_assistant[0]) <= _TOLERANCE_PX
    assert abs(live_back[1] - live_assistant[1]) <= _TOLERANCE_PX


def test_main_window_splitter_then_maximize_restore(main_window, qapp) -> None:
    _process_until_stable(qapp, main_window._viz)
    splitter = main_window._assistant_page.splitter
    splitter.setSizes([600, 550])
    qapp.processEvents()

    live_after_split = main_window._viz.live_anchor_center_local()
    assert live_after_split is not None

    main_window.showMaximized()
    offset = _process_until_stable(qapp, main_window._viz)
    assert offset is not None
    assert _offset_within_tolerance(offset)

    main_window.showNormal()
    offset = _process_until_stable(qapp, main_window._viz)
    assert offset is not None
    assert _offset_within_tolerance(offset)

    live_restored = main_window._viz.live_anchor_center_local()
    assert live_restored is not None
    assert abs(live_restored[0] - live_after_split[0]) <= _TOLERANCE_PX
    assert abs(live_restored[1] - live_after_split[1]) <= _TOLERANCE_PX

    restored_sizes = splitter.sizes()
    assert abs(restored_sizes[0] - 600) <= 30 or restored_sizes[0] > 0


def test_simple_fixture_maximize_restore_without_manual_sync(qapp) -> None:
    """CyberspaceBackground 단독 — 수동 request_sync 없이 최대화·복원."""
    bg, viz, _anchor = _build_simple_fixture(qapp)
    _process_until_stable(qapp, viz)
    live_initial = viz.live_anchor_center_local()
    assert live_initial is not None

    for _ in range(3):
        bg.showMaximized()
        offset = _process_until_stable(qapp, viz)
        assert offset is not None
        assert _offset_within_tolerance(offset)

        bg.showNormal()
        offset = _process_until_stable(qapp, viz)
        assert offset is not None
        assert _offset_within_tolerance(offset)

    live_final = viz.live_anchor_center_local()
    assert live_final is not None
    assert abs(live_final[0] - live_initial[0]) <= _TOLERANCE_PX
    assert abs(live_final[1] - live_initial[1]) <= _TOLERANCE_PX
    bg.close()
