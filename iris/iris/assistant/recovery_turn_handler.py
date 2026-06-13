"""앱 재시작 후 복구 명령 처리 — 계속 진행·상태 확인·작업 취소."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from iris.application.approval_service import _is_expired
from iris.application.recovery_commands import (
    RecoveryCommand,
    build_resume_slots,
    classify_recovery_command,
    format_recovery_status,
    resume_goal_from_snapshot,
    validate_resume_snapshot,
)
from iris.core.activity_sink import push_activity_line
from iris.core.context_manager import PendingComputerUseGoal
from iris.domain.execution.enums import ApprovalStatus
from iris.domain.task.enums import TaskStatus

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.assistant.turn_coordinator import TurnResult


def try_handle_recovery_turn(
    assistant: IrisAssistant,
    turn_id: str,
    user_text: str,
    logs: list[str],
    *,
    on_user_notify: Callable[[str], None] | None = None,
) -> TurnResult | None:
    """active_task_id 기반 복구 명령 처리. 해당 없으면 None."""
    from iris.assistant.turn_coordinator import TurnResult

    cmd = classify_recovery_command(user_text)
    if cmd is None:
        return None

    task_id = assistant.ctx.active_task_id
    if not task_id:
        return None

    bundle = getattr(assistant, "_task_runtime_bundle", None)
    if bundle is None:
        adapter = assistant._ensure_task_runtime()
        if adapter is None:
            return None
        bundle = getattr(assistant, "_task_runtime_bundle", None)
    if bundle is None:
        return None

    recoverable = bundle.recovery.list_recoverable_tasks()
    if not any(t.id == task_id for t in recoverable):
        snap_check = bundle.recovery.load_recovery_snapshot(task_id)
        if snap_check is None or snap_check.task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        ):
            assistant.ctx.active_task_id = None
            return None

    snap = bundle.recovery.load_recovery_snapshot(task_id)
    logs.append(f"recovery_cmd={cmd.value}")

    if cmd is RecoveryCommand.STATUS:
        if snap is None:
            return TurnResult(
                turn_id=turn_id,
                route="recovery",
                user_visible="Iris: 복구 정보를 찾을 수 없습니다.",
                early_ack=None,
                executed=False,
                logs=logs + ["recovery_status_missing"],
                store_history=True,
            )
        body = format_recovery_status(snap)
        push_activity_line("Recovery: status query.")
        return TurnResult(
            turn_id=turn_id,
            route="recovery",
            user_visible=f"Iris: 이전 작업 상태입니다.\n{body}",
            early_ack=None,
            executed=False,
            logs=logs + ["recovery_status"],
            store_history=True,
        )

    if cmd is RecoveryCommand.CANCEL:
        push_activity_line("Recovery: user cancelled task.")
        bundle.recovery.abandon_task(task_id)
        assistant.ctx.active_task_id = None
        assistant.ctx.clear_pending_cu()
        return TurnResult(
            turn_id=turn_id,
            route="recovery",
            user_visible="Iris: 작업을 취소했습니다.",
            early_ack=None,
            executed=False,
            logs=logs + ["recovery_cancel"],
            store_history=True,
        )

    # CONTINUE
    validation = validate_resume_snapshot(snap)
    if not validation.ok:
        return TurnResult(
            turn_id=turn_id,
            route="recovery",
            user_visible=f"Iris: {validation.message}",
            early_ack=None,
            executed=False,
            logs=logs + ["recovery_invalid_snapshot"],
            store_history=True,
        )

    assert snap is not None
    push_activity_line(f"Recovery: resume task_id={task_id[:8]}…")

    # RUNNING → INTERRUPTED 정규화 (비정상 종료)
    if snap.task.status == TaskStatus.RUNNING:
        bundle.tasks.mark_task_interrupted(snap.task, "app_restart")

    resumed = bundle.recovery.resume_task(task_id)
    if resumed is None:
        return TurnResult(
            turn_id=turn_id,
            route="recovery",
            user_visible="Iris: 작업을 재개하지 못했습니다.",
            early_ack=None,
            executed=False,
            logs=logs + ["recovery_resume_failed"],
            store_history=True,
        )

    # WAITING_APPROVAL — 기존 Proposal 유지, 만료 시 새 ApprovalRequest
    if snap.task.status == TaskStatus.WAITING_APPROVAL and snap.pending_approval:
        return _resume_waiting_approval(
            assistant,
            turn_id,
            snap,
            logs,
            bundle=bundle,
        )

    slots = build_resume_slots(snap)
    goal = resume_goal_from_snapshot(snap)
    assistant._ensure_task_runtime()
    reply = assistant.run_computer_use_loop(
        user_text,
        goal=goal,
        slots=slots,
        on_user_notify=on_user_notify,
    )
    user_visible, executed, extra_logs = _finalize_recovery_cu_reply(
        assistant, goal=goal, slots=slots, reply=reply
    )
    logs.extend(extra_logs)
    if not user_visible.startswith("Iris:"):
        user_visible = f"Iris: {user_visible}"
    return TurnResult(
        turn_id=turn_id,
        route="recovery",
        user_visible=user_visible,
        early_ack=None,
        executed=executed,
        logs=logs + ["recovery_continue"],
        store_history=True,
    )


def _resume_waiting_approval(
    assistant: IrisAssistant,
    turn_id: str,
    snap: Any,
    logs: list[str],
    *,
    bundle: Any,
) -> TurnResult:
    """WAITING_APPROVAL — 기존 Proposal 복원, 만료 시 새 승인 요청."""
    from iris.assistant.turn_coordinator import TurnResult

    pending_req = snap.pending_approval
    proposal = snap.latest_proposal
    if pending_req is None or proposal is None:
        return TurnResult(
            turn_id=turn_id,
            route="recovery",
            user_visible="Iris: 승인 정보가 불완전해 실행할 수 없습니다.",
            early_ack=None,
            executed=False,
            logs=logs + ["recovery_approval_incomplete"],
            store_history=True,
        )

    expired = _is_expired(pending_req)
    if expired:
        bundle.repos.approvals.update_status(
            pending_req.id, ApprovalStatus.EXPIRED
        )
        new_req = bundle.approvals.create_request(snap.task, proposal)
        pending_req = new_req
        logs.append("recovery_approval_refreshed")

    cp_snap = snap.checkpoint.snapshot if snap.checkpoint else {}
    goal = resume_goal_from_snapshot(snap)
    slots = build_resume_slots(snap)
    slots["_task_id"] = snap.task.id
    slots["_task_proposal_id"] = proposal.id
    slots["_task_approval_id"] = pending_req.id

    tool_name = proposal.tool_name
    params = dict(proposal.arguments)
    preview = cp_snap.get("preview") or tool_name

    assistant.ctx.pending_cu = PendingComputerUseGoal(
        goal=goal,
        risk_hint="critical",
        prompt=f"'{tool_name}' 실행 승인이 필요합니다. '진행해줘'라고 말씀해 주세요.",
        slots=slots,
        pending_tool_name=tool_name,
        pending_tool_params=params,
        pending_tool_preview=preview,
        pending_plan_index=int(cp_snap.get("step_index", 0)),
    )
    msg = (
        f"Iris: 이전 작업이 승인 대기 중입니다.\n"
        f"도구: {tool_name}\n"
        f"{'이전 승인이 만료되어 새 승인이 필요합니다. ' if expired else ''}"
        f"계속하려면 '진행해줘' 또는 '계속 진행'이라고 말씀해 주세요."
    )
    return TurnResult(
        turn_id=turn_id,
        route="recovery",
        user_visible=msg,
        early_ack=None,
        executed=False,
        logs=logs + ["recovery_waiting_approval_restored"],
        store_history=True,
    )


def _finalize_recovery_cu_reply(
    assistant: IrisAssistant,
    *,
    goal: str,
    slots: dict[str, Any],
    reply: str,
) -> tuple[str, bool, list[str]]:
    """CU 재개 결과 정리."""
    from iris.assistant.turn_coordinator import _finalize_cu_reply

    return _finalize_cu_reply(
        assistant.ctx,
        goal=goal,
        slots=slots,
        reply=reply,
        risk_hint="low",
    )
