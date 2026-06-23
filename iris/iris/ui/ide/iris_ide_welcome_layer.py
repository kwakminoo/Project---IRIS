"""IDE Empty Home — Cursor 스타일 웰컴 화면 (폴더 미열림 상태)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
  QFileDialog,
  QHBoxLayout,
  QInputDialog,
  QLabel,
  QPushButton,
  QSizePolicy,
  QVBoxLayout,
  QWidget,
)

from iris.storage.ide_recent_folders import (
  list_recent_folders,
  record_opened_folder,
  truncate_path_middle,
)
from iris.ui.ide.ide_layout_constants import (
  THEIA_ACTIVITY_BAR_WIDTH,
  WELCOME_ORB_SLOT_SIZE,
)
from iris.ui.ide.ide_orb_placement import apply_welcome_orb_geometry, mount_orb, unmount_orb
from iris.ui.ide.ide_overlay_mouse import ensure_interactive_overlay, set_visual_only_overlay
from iris.ui.ide.ide_welcome_icons import WelcomeOutlineIcon
from iris.ui.ide.iris_orb_widget import IrisOrbWidget
from iris.ui.theme_tokens import TOKENS

# Cursor 웰컴 — 가로로 긴 액션 카드
_WELCOME_MAX_WIDTH = 920
_BTN_MIN_WIDTH = 148
_BTN_MIN_HEIGHT = 88
_SECTION_GAP = 15
# DragTitle 25px → 2배
_TITLE_FONT_PX = 50

# 좌·우 사이드 chrome과 동일 톤 (Theia top panel · panel glass)
_BTN_BG = "rgba(5, 12, 26, 0.25)"
_BTN_BORDER = TOKENS.border_subtle


class _WelcomeActionButton(QPushButton):
  def __init__(self, icon_kind: str, label: str, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IdeWelcomeActionButton")
    self.setMinimumSize(_BTN_MIN_WIDTH, _BTN_MIN_HEIGHT)
    self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    self.setCursor(Qt.CursorShape.PointingHandCursor)
    self.setFlat(True)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(14, 14, 14, 12)
    lay.setSpacing(10)
    lay.addWidget(WelcomeOutlineIcon(icon_kind, self), 0, Qt.AlignmentFlag.AlignHCenter)
    lbl = QLabel(label, self)
    lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    lbl.setStyleSheet(
      f"color: {TOKENS.text_primary}; font-size: 13px; background: transparent;"
    )
    lay.addWidget(lbl)
    self._label = lbl

    self.setStyleSheet(
      f"QPushButton#IdeWelcomeActionButton {{"
      f" background: {_BTN_BG};"
      f" border: 1px solid {_BTN_BORDER};"
      f" border-radius: 8px;"
      f"}}"
      f"QPushButton#IdeWelcomeActionButton:hover {{"
      f" background: {TOKENS.panel_hover};"
      f" border-color: {TOKENS.border_color};"
      f"}}"
      f"QPushButton#IdeWelcomeActionButton:pressed {{"
      f" background: rgba(37, 99, 235, 0.28);"
      f" border-color: {TOKENS.neon_cyan};"
      f"}}"
    )

  def label_text(self) -> str:
    return self._label.text()


class IrisIdeWelcomeLayer(QWidget):
  """
  폴더 미열림 시 중앙 웰컴 — interactive overlay, 배경 투명.
  좌측 Activity Bar(48px)는 마우스 투과. 구체는 IRIS IDE 타이틀 좌측.
  """

  folder_opened = pyqtSignal(str)
  folder_created = pyqtSignal(str)

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IrisIdeWelcomeLayer")
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self.setAutoFillBackground(False)

    root = QHBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    self._activity_pass = QWidget(self)
    self._activity_pass.setFixedWidth(THEIA_ACTIVITY_BAR_WIDTH)
    set_visual_only_overlay(self._activity_pass)
    root.addWidget(self._activity_pass, 0)

    self._panel = QWidget(self)
    self._panel.setObjectName("IrisIdeWelcomePanel")
    ensure_interactive_overlay(self._panel)
    self._panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self._panel.setAutoFillBackground(False)
    self._panel.setStyleSheet("background: transparent;")
    root.addWidget(self._panel, 1)

    panel_lay = QVBoxLayout(self._panel)
    panel_lay.setContentsMargins(32, 48, 32, 32)
    panel_lay.setSpacing(0)
    panel_lay.addStretch(2)

    content = QWidget(self._panel)
    content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    content.setMaximumWidth(_WELCOME_MAX_WIDTH)
    content_lay = QVBoxLayout(content)
    content_lay.setContentsMargins(0, 0, 0, 0)
    content_lay.setSpacing(0)

    title_wrap = QWidget(content)
    title_wrap.setFixedHeight(WELCOME_ORB_SLOT_SIZE)
    title_wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    title_row = QHBoxLayout(title_wrap)
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(14)
    title_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    self._orb_slot = QWidget(title_wrap)
    self._orb_slot.setFixedSize(WELCOME_ORB_SLOT_SIZE, WELCOME_ORB_SLOT_SIZE)
    self._orb_slot_lay = QVBoxLayout(self._orb_slot)
    self._orb_slot_lay.setContentsMargins(0, 0, 0, 0)
    title_row.addWidget(self._orb_slot, 0, Qt.AlignmentFlag.AlignVCenter)

    self._title = QLabel("IRIS IDE", title_wrap)
    self._title.setObjectName("IdeWelcomeTitle")
    self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    self._title.setStyleSheet(
      f"color: {TOKENS.text_accent};"
      f" font-size: {_TITLE_FONT_PX}px;"
      " font-weight: 400;"
      " letter-spacing: 4px;"
      " background: transparent;"
    )
    title_row.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)
    content_lay.addWidget(title_wrap)
    content_lay.addSpacing(_SECTION_GAP)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(12)
    self.btn_open_folder = _WelcomeActionButton("folder", "Open folder", content)
    self.btn_create_folder = _WelcomeActionButton("folder_plus", "Create folder", content)
    self.btn_connect_ssh = _WelcomeActionButton("terminal", "Connect via SSH", content)
    self.btn_open_folder.clicked.connect(self._pick_open_folder)
    self.btn_create_folder.clicked.connect(self._pick_create_folder)
    btn_row.addWidget(self.btn_open_folder, 1)
    btn_row.addWidget(self.btn_create_folder, 1)
    btn_row.addWidget(self.btn_connect_ssh, 1)
    content_lay.addLayout(btn_row)
    content_lay.addSpacing(_SECTION_GAP)

    recent_hdr = QHBoxLayout()
    recent_lbl = QLabel("Recent projects")
    recent_lbl.setStyleSheet(
      f"color: {TOKENS.text_secondary}; font-size: 13px; background: transparent;"
    )
    recent_hdr.addWidget(recent_lbl)
    recent_hdr.addStretch(1)
    content_lay.addLayout(recent_hdr)

    self._recent_rows: list[tuple[QLabel, QLabel]] = []
    recent_box = QVBoxLayout()
    recent_box.setSpacing(6)
    for _ in range(5):
      row = QHBoxLayout()
      name_lbl = QLabel("")
      name_lbl.setStyleSheet(
        f"color: {TOKENS.text_primary}; font-size: 13px; background: transparent;"
      )
      path_lbl = QLabel("")
      path_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
      path_lbl.setStyleSheet(
        f"color: {TOKENS.text_muted}; font-size: 12px; background: transparent;"
      )
      row.addWidget(name_lbl, 0)
      row.addStretch(1)
      row.addWidget(path_lbl, 0)
      recent_box.addLayout(row)
      self._recent_rows.append((name_lbl, path_lbl))
    content_lay.addLayout(recent_box)

    panel_lay.addWidget(content, 0, Qt.AlignmentFlag.AlignHCenter)
    panel_lay.addStretch(3)

    self.refresh_recent_folders()

  def mount_orb(self, orb: IrisOrbWidget) -> None:
    apply_welcome_orb_geometry(orb)
    self._orb_slot.setFixedSize(WELCOME_ORB_SLOT_SIZE, WELCOME_ORB_SLOT_SIZE)
    mount_orb(self._orb_slot, self._orb_slot_lay, orb)
    self._orb_slot.show()

  def unmount_orb(self, orb: IrisOrbWidget) -> None:
    unmount_orb(self._orb_slot_lay, orb)
    self._orb_slot.hide()

  def _pick_open_folder(self) -> None:
    path = QFileDialog.getExistingDirectory(self, "Open folder")
    if path:
      record_opened_folder(Path(path))
      self.refresh_recent_folders()
      self.folder_opened.emit(path)

  def _pick_create_folder(self) -> None:
    parent = QFileDialog.getExistingDirectory(self, "Create folder — 상위 디렉터리 선택")
    if not parent:
      return
    name, ok = QInputDialog.getText(self, "Create folder", "Folder name:")
    if not ok or not name.strip():
      return
    new_dir = Path(parent) / name.strip()
    new_dir.mkdir(parents=True, exist_ok=True)
    record_opened_folder(new_dir)
    self.refresh_recent_folders()
    self.folder_created.emit(str(new_dir.resolve()))

  def refresh_recent_folders(self) -> None:
    recent = list_recent_folders(5)
    for i, (name_lbl, path_lbl) in enumerate(self._recent_rows):
      if i < len(recent):
        name, path = recent[i]
        name_lbl.setText(name)
        path_lbl.setText(truncate_path_middle(path))
      else:
        name_lbl.setText("")
        path_lbl.setText("")

  def set_workspace_label(self, text: str) -> None:
    del text
