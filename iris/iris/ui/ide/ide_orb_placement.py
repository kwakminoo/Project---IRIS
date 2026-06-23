"""IDE 공유 Iris 구체 — 웰컴 타이틀 / 우측 Dock 배치."""

from __future__ import annotations

from PyQt6.QtWidgets import QLayout, QVBoxLayout, QWidget

from iris.ui.ide.ide_layout_constants import (
  ASSISTANT_DOCK_ORB_HEIGHT,
  ASSISTANT_DOCK_ORB_TOP_PAD,
  DOCK_ORB_SCALE,
  WELCOME_ORB_SLOT_SIZE,
)
from iris.ui.ide.iris_orb_widget import IrisOrbWidget
from iris.ui.particle_visualizer import orb_size_scale_for_square_fill


def _clear_layout(layout: QLayout) -> None:
  while layout.count():
    item = layout.takeAt(0)
    if item.widget() is not None:
      item.widget().setParent(None)


def apply_welcome_orb_geometry(orb: IrisOrbWidget) -> None:
  """웰컴 타이틀 구체 — 슬롯 변과 글로우 외곽을 일치."""
  size = WELCOME_ORB_SLOT_SIZE
  orb.setFixedSize(size, size)
  core = orb.particle_core()
  lay = orb.layout()
  if lay is not None:
    lay.setContentsMargins(0, 0, 0, 0)
  core.setMinimumSize(size, size)
  core.setMaximumSize(size, size)
  half = size / 2
  core.set_custom_center(half, half)
  core.set_size_scale(orb_size_scale_for_square_fill(size))


def apply_dock_orb_geometry(orb: IrisOrbWidget) -> None:
  inner_h = ASSISTANT_DOCK_ORB_HEIGHT - ASSISTANT_DOCK_ORB_TOP_PAD
  orb.setFixedHeight(ASSISTANT_DOCK_ORB_HEIGHT)
  core = orb.particle_core()
  core.clear_custom_center()
  lay = orb.layout()
  if lay is not None:
    lay.setContentsMargins(0, ASSISTANT_DOCK_ORB_TOP_PAD, 0, 0)
  core.setMinimumHeight(inner_h)
  core.setMaximumHeight(inner_h)
  core.set_size_scale(DOCK_ORB_SCALE)


def mount_orb(slot: QWidget, slot_layout: QVBoxLayout, orb: IrisOrbWidget) -> None:
  _clear_layout(slot_layout)
  orb.setParent(slot)
  slot_layout.setContentsMargins(0, 0, 0, 0)
  slot_layout.setSpacing(0)
  slot_layout.addWidget(orb)
  orb.show()


def unmount_orb(slot_layout: QVBoxLayout, orb: IrisOrbWidget) -> None:
  _clear_layout(slot_layout)
  orb.setParent(None)
  orb.hide()
