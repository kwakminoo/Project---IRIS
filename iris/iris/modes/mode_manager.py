"""모드 매니저."""

from __future__ import annotations

from enum import Enum, auto


class IrisMode(Enum):
    NORMAL = auto()
    WORK = auto()
    GAME = auto()
    CREATIVE = auto()


class ModeManager:
    def __init__(self) -> None:
        self.active = IrisMode.NORMAL

    def set_mode(self, mode: IrisMode) -> None:
        self.active = mode
