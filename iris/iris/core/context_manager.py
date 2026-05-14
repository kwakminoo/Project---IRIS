"""다턴 대화(모드 플로우·승인 대기) 컨텍스트."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class DialogueStep(Enum):
    NONE = auto()
    WORK_ASK_TASK = auto()
    WORK_ASK_APPS = auto()
    WORK_WAIT_APPROVAL = auto()
    GAME_ASK_TITLE = auto()
    GAME_ASK_SIDE_APPS = auto()
    GAME_WAIT_APPROVAL = auto()
    CREATIVE_ASK_TYPE = auto()
    CREATIVE_ASK_APPS = auto()
    CREATIVE_WAIT_APPROVAL = auto()
    MONITOR_WAIT_APPROVAL = auto()


@dataclass
class PendingMonitoringAction:
    """모니터링으로 인한 승인 대기 (키보드 입력 등)."""

    event_id: int
    target_id: int
    focus_hint: str
    suggested_input: str
    category: str


@dataclass
class PendingPlan:
    """승인 대기 중인 실행 계획."""

    title: str
    preset_id: str
    app_keys: List[str]
    work_type_label: str


@dataclass
class DialogueContext:
    """세션 단계 및 슬롯."""

    step: DialogueStep = DialogueStep.NONE
    pending: Optional[PendingPlan] = None
    pending_monitor: Optional[PendingMonitoringAction] = None
    slots: Dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.step = DialogueStep.NONE
        self.pending = None
        self.pending_monitor = None
        self.slots.clear()
