"""IDE 웰컴 화면·최근 폴더 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from iris.storage import ide_recent_folders as recent_mod
from iris.ui.ide.ide_layout_constants import (
  ASSISTANT_DOCK_ORB_HEIGHT,
  WELCOME_ORB_SLOT_SIZE,
)
from iris.ui.ide.iris_ide_welcome_layer import IrisIdeWelcomeLayer
from iris.ui.workspaces.ide_workspace_page import IdeWorkspacePage


@pytest.fixture(scope="module")
def qapp():
  app = QApplication.instance()
  if app is None:
    app = QApplication([])
  return app


def test_welcome_has_action_buttons(qapp) -> None:
  layer = IrisIdeWelcomeLayer()
  assert layer.btn_open_folder.label_text() == "Open folder"
  assert layer.btn_create_folder.label_text() == "Create folder"
  assert "SSH" in layer.btn_connect_ssh.label_text()


def test_welcome_activity_bar_pass_through(qapp) -> None:
  layer = IrisIdeWelcomeLayer()
  assert layer._activity_pass.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
  assert not layer._panel.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_recent_folders_roundtrip(tmp_path: Path, monkeypatch) -> None:
  store = tmp_path / "recent.json"
  monkeypatch.setattr(recent_mod, "_STORE", store)
  recent_mod.record_opened_folder(tmp_path / "ProjectA")
  recent_mod.record_opened_folder(tmp_path / "ProjectB")
  rows = recent_mod.list_recent_folders(5)
  assert len(rows) == 2
  assert rows[0][0] == "ProjectB"
  assert rows[1][0] == "ProjectA"


def test_welcome_shows_recent_folders(qapp, tmp_path: Path, monkeypatch) -> None:
  store = tmp_path / "recent.json"
  monkeypatch.setattr(recent_mod, "_STORE", store)
  recent_mod.record_opened_folder(tmp_path / "IRIS")
  layer = IrisIdeWelcomeLayer()
  layer.refresh_recent_folders()
  assert layer._recent_rows[0][0].text() == "IRIS"


def test_ide_page_welcome_visible_by_default(qapp) -> None:
  page = IdeWorkspacePage()
  page.resize(1280, 800)
  page.show()
  qapp.processEvents()
  assert page.empty_home.isVisible()
  assert page.iris_orb.parent() is page.empty_home._orb_slot


def test_folder_open_moves_orb_to_dock(qapp) -> None:
  page = IdeWorkspacePage()
  page.resize(1280, 800)
  page.show()
  qapp.processEvents()
  page.set_workspace_folder_open(True)
  qapp.processEvents()
  assert not page.empty_home.isVisible()
  assert page.coding_panel.orb is page.iris_orb
  dock = page.coding_panel
  assert dock._orb_slot.isVisible()
  assert dock._orb_slot.height() == ASSISTANT_DOCK_ORB_HEIGHT
  assert page.iris_orb.isVisible()
  assert page.iris_orb.height() == ASSISTANT_DOCK_ORB_HEIGHT


def test_welcome_orb_250px_slot(qapp) -> None:
  page = IdeWorkspacePage()
  page.resize(1280, 800)
  page.show()
  qapp.processEvents()
  assert page.empty_home._orb_slot.height() == WELCOME_ORB_SLOT_SIZE
  assert page.iris_orb.height() == WELCOME_ORB_SLOT_SIZE
  assert page.iris_orb.width() == WELCOME_ORB_SLOT_SIZE


def test_welcome_orb_visual_fills_slot(qapp) -> None:
  from iris.ui.particle_visualizer import _VISUAL_HALO_FACTOR

  page = IdeWorkspacePage()
  page.resize(1280, 800)
  page.show()
  qapp.processEvents()
  core = page.iris_orb.particle_core()
  core._recompute_geometry()
  halo_diameter = core._core_r * _VISUAL_HALO_FACTOR * 2
  assert abs(halo_diameter - WELCOME_ORB_SLOT_SIZE) < 1.0
  cx, cy = core.effective_center()
  assert abs(cx - WELCOME_ORB_SLOT_SIZE / 2) < 1.0
  assert abs(cy - WELCOME_ORB_SLOT_SIZE / 2) < 1.0


def test_welcome_title_to_buttons_spacing(qapp) -> None:
  """타이틀 행(구체+텍스트) 바로 아래 버튼까지 레이아웃 간격 15px."""
  layer = IrisIdeWelcomeLayer()
  layer.resize(900, 700)
  layer.show()
  qapp.processEvents()
  orb_slot = layer._orb_slot
  btn = layer.btn_open_folder
  title_wrap = orb_slot.parentWidget()
  assert title_wrap is not None
  # QRect.bottom()는 inclusive — exclusive 간격은 y+height 기준
  gap = btn.geometry().top() - title_wrap.geometry().y() - title_wrap.geometry().height()
  assert gap == _SECTION_GAP


_SECTION_GAP = 15  # iris_ide_welcome_layer._SECTION_GAP 와 동기
