"""모니터링 이벤트 → DialogueAgent 선제 대화 제안."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from iris.core.context_manager import DialogueStep, PendingMonitoringAction

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.assistant.dialogue_agent import DialogueAgent

# 채팅·알림 패널에 노출할 카테고리
_CHAT_CATEGORIES = frozenset(
    {
        "APPROVAL_WAITING",
        "ERROR_DETECTED",
        "TASK_STALLED",
        "RESPONSE_READY",
        "USER_ACTION_REQUIRED",
        "GENERATION_FAILED",
    }
)
# 승인 대기(pending_monitor)로 전환할 카테고리
_PENDING_CATEGORIES = frozenset({"APPROVAL_WAITING", "USER_ACTION_REQUIRED"})


@dataclass
class ProactiveMonitorResult:
    """선제 모니터링 제안 처리 결과."""

    proposal: str  # 채팅·TTS 본문 (Iris: 접두사 없음)
    show_in_chat: bool
    pending_set: bool


def should_suppress_proactive_chat(dialogue_ctx: Any) -> bool:
    """
    Computer Use·다른 승인 대기 중에는 채팅 선제 제안 억제.
    CU 루프에는 cu_hint_injector의 monitor_hint observation만 주입.
    """
    if dialogue_ctx is None:
        return False
    if getattr(dialogue_ctx, "pending_cu", None) is not None:
        return True
    step = getattr(dialogue_ctx, "step", None)
    if step in (
        DialogueStep.WORK_WAIT_APPROVAL,
        DialogueStep.GAME_WAIT_APPROVAL,
        DialogueStep.CREATIVE_WAIT_APPROVAL,
        DialogueStep.ACTION_WAIT_APPROVAL,
        DialogueStep.MONITOR_WAIT_APPROVAL,
    ):
        return True
    return False


def try_proactive_suggestion_from_event(
    *,
    category: str,
    target_title: str,
    recommended_action: str,
    alert_message: str = "",
    dialogue_ctx: Any = None,
    dialogue: DialogueAgent | None = None,
) -> str | None:
    """
    MonitorManager.alert_emitted 후 DialogueAgent 제안 문장 생성.
    억제 조건이면 None (CU monitor_hint만 사용).
    """
    if should_suppress_proactive_chat(dialogue_ctx):
        return None
    if dialogue is None:
        from iris.monitoring.dialogue_bridge import monitoring_proposal_message

        return monitoring_proposal_message(
            category, target_title, recommended_action, alert_message
        )
    return dialogue.monitor_proposal(
        category,
        target_title,
        recommended_action,
        alert_message=alert_message,
    )


def dispatch_proactive_monitor_event(
    assistant: IrisAssistant,
    dialogue: DialogueAgent,
    *,
    title: str,
    message: str,
    category: str,
    target_id: int,
    focus_hint: str,
    recommended: str,
    event_id: int,
) -> ProactiveMonitorResult | None:
    """
    UI·테스트 공용 — 제안 문장 생성, memory 기록, pending_monitor 설정.
    TurnCoordinator/DialogueAgent 경로와 동일한 한국어 톤 유지.
    """
    proposal = try_proactive_suggestion_from_event(
        category=category,
        target_title=title,
        recommended_action=recommended,
        alert_message=message,
        dialogue_ctx=assistant.ctx,
        dialogue=dialogue,
    )
    if not proposal:
        return None

    assistant.memory.add_long_term_summary(
        "monitor", proposal[:240], source_hint=title[:80]
    )
    assistant.memory.save_task_session(
        current_goal=f"모니터링: {title}",
        observations=[proposal[:200]],
    )

    show_in_chat = category in _CHAT_CATEGORIES
    pending_set = False
    if category in _PENDING_CATEGORIES:
        sug = "y"
        if "n" in (recommended or "").lower() and "y" not in (recommended or "").lower():
            sug = ""
        pm = PendingMonitoringAction(
            event_id=event_id,
            target_id=target_id,
            focus_hint=focus_hint,
            suggested_input=sug,
            category=category,
            natural_language=proposal,
        )
        pending_set = assistant.set_monitor_pending(pm)

    return ProactiveMonitorResult(
        proposal=proposal,
        show_in_chat=show_in_chat,
        pending_set=pending_set,
    )
