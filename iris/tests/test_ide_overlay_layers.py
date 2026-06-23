"""IDE 오버레이 레이어·마우스 경계·뒤로가기 연결 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from iris.ui.ide.embedded_theia_view import EmbeddedTheiaView, TheiaViewState
from iris.ui.ide.ide_activity_back_button import IdeActivityBackButton
from iris.ui.ide.ide_back_navigation_controller import IdeBackNavigationController
from iris.ui.ide.ide_shell_layout import IdeShellLayout
from iris.ui.ide.iris_ide_welcome_layer import IrisIdeWelcomeLayer
from iris.ui.workspaces.ide_workspace_page import IdeWorkspacePage


@pytest.fixture(scope="module")
def qapp():
  app = QApplication.instance()
  if app is None:
    app = QApplication([])
  return app


def test_welcome_home_activity_pass_is_transparent(qapp) -> None:
  layer = IrisIdeWelcomeLayer()
  assert layer._activity_pass.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
  assert not layer._panel.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_back_button_is_interactive_overlay(qapp) -> None:
  btn = IdeActivityBackButton()
  assert not btn.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
  assert btn.minimumWidth() >= 48
  assert btn.minimumHeight() >= 48
  assert btn.accessibleName()
  assert btn.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_ide_shell_has_all_layers(qapp) -> None:
  shell = IdeShellLayout()
  assert shell.theia is not None
  assert shell.center_orb is not None
  assert shell.back_button is not None
  assert shell.assistant_dock is not None
  host = shell.theia_host
  assert host.theia is shell.theia
  assert host.center_orb is shell.center_orb
  assert host.back_button is shell.back_button


def test_back_button_wires_to_theia_back(qapp) -> None:
  page = IdeWorkspacePage()
  received: list[bool] = []
  page.theia_back.connect(lambda: received.append(True))
  page.back_button.back_clicked.emit()
  qapp.processEvents()
  assert received == [True]


def test_back_navigation_controller_unifies_sources(qapp) -> None:
  btn = IdeActivityBackButton()
  view = EmbeddedTheiaView()
  ctrl = IdeBackNavigationController()
  received: list[int] = []
  ctrl.back_requested.connect(lambda: received.append(1))
  ctrl.connect_pyqt_button(btn)
  ctrl.connect_theia_view(view)

  btn.back_clicked.emit()
  view.back_to_assistant_requested.emit()
  qapp.processEvents()
  assert received == [1, 1]


def test_empty_home_welcome_visible(qapp) -> None:
  page = IdeWorkspacePage()
  page.resize(1280, 800)
  page.show()
  qapp.processEvents()
  assert page.empty_home.isVisible()
  assert not page.empty_home._panel.testAttribute(
    Qt.WidgetAttribute.WA_TransparentForMouseEvents
  )


def test_editor_mode_hides_center_orb(qapp) -> None:
  page = IdeWorkspacePage()
  page.resize(1280, 800)
  page.show()
  qapp.processEvents()
  page.show_editor_with_assistant()
  qapp.processEvents()
  assert not page.empty_home.isVisible()
  assert page.theia.isVisible()


def test_loading_overlay_hidden_after_ready_path(qapp) -> None:
  """WebEngine 없이 overlay show/hide API 검증 — READY 후 hide는 수동·E2E로 보완."""
  from PyQt6.QtWidgets import QFrame

  view = EmbeddedTheiaView()
  view.show()
  qapp.processEvents()
  assert not view.is_loading_overlay_visible()

  view._loading_overlay = QFrame(view)  # noqa: SLF001
  view._show_loading_overlay("test")  # noqa: SLF001
  qapp.processEvents()
  assert view.is_loading_overlay_visible()

  view._hide_loading_overlay()  # noqa: SLF001
  assert not view.is_loading_overlay_visible()

  view._set_state(TheiaViewState.READY, force=True)  # noqa: SLF001
  assert not view.is_loading_overlay_visible()
