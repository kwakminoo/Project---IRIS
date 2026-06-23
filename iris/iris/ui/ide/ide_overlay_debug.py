"""IDE 오버레이 클릭 디버그 — IRIS_IDE_OVERLAY_DEBUG=1 일 때만 활성."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication

if TYPE_CHECKING:
  from iris.ui.ide.ide_shell_layout import TheiaIdeHost

logger = logging.getLogger(__name__)

_ENV_FLAG = "IRIS_IDE_OVERLAY_DEBUG"


def overlay_debug_enabled() -> bool:
  return os.environ.get(_ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def _widget_chain(widget: object | None) -> str:
  parts: list[str] = []
  w = widget
  while w is not None:
    name = getattr(w, "objectName", lambda: "")() or type(w).__name__
    parts.append(name)
    w = w.parent() if hasattr(w, "parent") else None
  return " > ".join(parts)


class IdeOverlayClickDebugFilter(QObject):
  """TheiaIdeHost 클릭 시 최상위 위젯·레이어 소유 여부를 로그."""

  def __init__(self, host: TheiaIdeHost, parent: QObject | None = None) -> None:
    super().__init__(parent)
    self._host = host

  def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
    if not overlay_debug_enabled():
      return False
    if event.type() not in {
      QEvent.Type.MouseButtonPress,
      QEvent.Type.MouseButtonRelease,
    }:
      return False

    app = QApplication.instance()
    if app is None:
      return False

    pos = QCursor.pos()
    top = app.widgetAt(pos)
    center_orb = self._host.welcome_home
    back_button = self._host.back_button
    theia = self._host.theia

    orb_hit = center_orb.isVisible() and not center_orb.testAttribute(
      Qt.WidgetAttribute.WA_TransparentForMouseEvents
    )
    local = back_button.mapFromGlobal(pos)
    back_hit = back_button.isVisible() and back_button.rect().contains(local)
    line = (
      f"[IDE overlay debug] pos=({pos.x()},{pos.y()}) "
      f"top={_widget_chain(top)} "
      f"center_orb_visible={center_orb.isVisible()} "
      f"center_orb_transparent={center_orb.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)} "
      f"center_orb_would_block={orb_hit} "
      f"back_button_hit={back_hit} "
      f"theia={theia.objectName()}"
    )
    logger.info(line)
    return False
