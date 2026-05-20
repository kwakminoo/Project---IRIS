"""다턴 대화(모드 플로우·승인 대기) 컨텍스트."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from iris.core.command_router import CommandKind


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
    # 단일 액션(앱 실행·파일·자동화 등) 승인 대기
    ACTION_WAIT_APPROVAL = auto()


@dataclass
class PendingMonitoringAction:
    """모니터링으로 인한 승인 대기 (키보드 입력 등)."""

    event_id: int
    target_id: int
    focus_hint: str
    suggested_input: str
    category: str
    natural_language: str = ""  # 대화에 제시할 제안 문장


@dataclass
class PendingAutomationTool:
    """자동화 ToolRegistry 승인 대기."""

    tool_name: str
    params: Dict[str, Any]
    summary: str
    preview: str


@dataclass
class PendingPlan:
    """승인 대기 중인 실행 계획."""

    title: str
    preset_id: str
    app_keys: List[str]
    work_type_label: str


@dataclass
class PendingUserAction:
    """단일 실행 승인 대기 (OpenClaw 등 백엔드는 사용자에게 노출하지 않음)."""

    command_kind: "CommandKind"
    summary: str
    user_original_text: str
    app_key: Optional[str] = None
    display_name: Optional[str] = None


@dataclass
class PendingComputerUseGoal:
    """Computer Use 승인 대기 — 후속 발화·CU 중간 CRITICAL 도구 1스텝 실행 대기."""

    goal: str
    risk_hint: str = "low"  # low | medium | high | critical
    prompt: str = ""  # 사용자에게 제시한 확인 문구
    require_rule_approval: bool = False  # 레거시 — LLM 승인 차단에 사용하지 않음
    slots: Dict[str, Any] = field(default_factory=dict)
    # CRITICAL 도구 승인 후 1스텝만 실행 (CU 루프 재시작 방지)
    pending_tool_name: str = ""
    pending_tool_params: Dict[str, Any] = field(default_factory=dict)
    pending_tool_preview: str = ""

    @property
    def has_pending_tool(self) -> bool:
        return bool(self.pending_tool_name.strip())


@dataclass
class DialogueContext:
    """세션 단계 및 슬롯."""

    step: DialogueStep = DialogueStep.NONE
    pending: Optional[PendingPlan] = None
    pending_action: Optional[PendingUserAction] = None
    pending_monitor: Optional[PendingMonitoringAction] = None
    pending_automation: Optional[PendingAutomationTool] = None
    pending_cu: Optional[PendingComputerUseGoal] = None
    slots: Dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.step = DialogueStep.NONE
        self.pending = None
        self.pending_action = None
        self.pending_monitor = None
        self.pending_automation = None
        self.pending_cu = None
        self.slots.clear()

    def clear_pending_cu(self) -> None:
        """CU 승인 대기만 해제 (다른 멀티턴·자동화 상태는 유지)."""
        self.pending_cu = None
