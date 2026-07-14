"""Obsidian Workspace — 파티클 구체 + 우측 Iris Assistant Dock."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from iris.core.state_machine import AppState
from iris.ui.ide.ide_layout_constants import (
    ASSISTANT_DOCK_DEFAULT_WIDTH,
    ASSISTANT_DOCK_MAX_WIDTH,
    ASSISTANT_DOCK_MIN_WIDTH,
)
from iris.ui.ide.iris_assistant_dock import IrisAssistantDock
from iris.ui.knowledge.obsidian_particle_orb import ObsidianOrbNode, ObsidianParticleOrb


class ObsidianWorkspacePage(QWidget):
    """
    Obsidian 모드 레이아웃 — IDE와 동일 골격.
    [ 파티클 3D 구체 (stretch) | Iris 구체·채팅 Dock (fixed) ]
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianWorkspacePage")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.orb = ObsidianParticleOrb(self)
        self.assistant_dock = IrisAssistantDock(self)
        self.assistant_dock.set_workspace_label("Iris Wiki")
        self.assistant_dock.setFixedWidth(ASSISTANT_DOCK_DEFAULT_WIDTH)

        root.addWidget(self.orb, 1)
        root.addWidget(self.assistant_dock, 0)

    def set_notes(self, notes: list[ObsidianOrbNode]) -> None:
        """지식 노트로 중앙 구체·Dock 라벨 갱신."""
        self.orb.set_notes(notes)
        n = len(notes)
        self.assistant_dock.set_workspace_label(
            f"Iris Wiki · {n} notes" if n else "Iris Wiki · no notes"
        )

    def set_view_mode(self, mode: str) -> None:
        """중앙 시각화 2d / 3d."""
        self.orb.set_view_mode(mode)

    @property
    def note_selected(self):
        return self.orb.note_selected

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        total = max(self.width(), 1)
        dock_w = ASSISTANT_DOCK_DEFAULT_WIDTH
        if total - dock_w < 320:
            dock_w = max(ASSISTANT_DOCK_MIN_WIDTH, total - 320)
        dock_w = max(ASSISTANT_DOCK_MIN_WIDTH, min(dock_w, ASSISTANT_DOCK_MAX_WIDTH))
        self.assistant_dock.setFixedWidth(dock_w)

    def set_app_state(self, state: AppState) -> None:
        self.assistant_dock.set_app_state(state)

    def set_mic_level(self, level: float) -> None:
        self.assistant_dock.set_mic_level(level)

    def active_chat(self):
        return self.assistant_dock.chat
