"""Iris 대화·모드·실행 오케스트레이션."""

from __future__ import annotations

import re

from iris.assistant.safety_guard import quick_block_user_text
from iris.assistant.task_planner import plan_from_preset
from iris.automation.action_executor import ActionExecutor
from iris.config.preset_modes import find_preset
from iris.core.command_router import CommandKind, classify_command
from iris.core.context_manager import (
    DialogueContext,
    DialogueStep,
    PendingMonitoringAction,
    PendingPlan,
)
from iris.core.recent_work_manager import format_recent_work_suggestion, seed_demo_recent_work
from iris.modes import creative_mode, game_mode, work_mode
from iris.storage.database import Database


def _is_approval(text: str) -> bool:
    t = text.strip().lower()
    return t in {"응", "네", "좋아", "승인", "실행", "확인", "yes", "ok", "y", "ㅇㅇ"}


def _is_reject(text: str) -> bool:
    t = text.strip().lower()
    return t in {"아니", "취소", "no", "n", "싫어"}


class IrisAssistant:
    """텍스트/음성 공통 처리."""

    def __init__(
        self,
        db: Database,
        executor: ActionExecutor,
    ) -> None:
        self._db = db
        self._executor = executor
        self.ctx = DialogueContext()
        seed_demo_recent_work(db)

    def set_monitor_pending(self, pending: PendingMonitoringAction) -> bool:
        """모니터링 승인 대기. 작업/게임 승인 대기 중이면 True 반환하지 않고 스킵."""
        if self.ctx.step in (
            DialogueStep.WORK_WAIT_APPROVAL,
            DialogueStep.GAME_WAIT_APPROVAL,
            DialogueStep.CREATIVE_WAIT_APPROVAL,
        ):
            return False
        self.ctx.pending = None
        self.ctx.pending_monitor = pending
        self.ctx.step = DialogueStep.MONITOR_WAIT_APPROVAL
        return True

    def handle_user_text(self, text: str) -> str:
        """사용자 입력 한 턴 처리."""
        block = quick_block_user_text(text)
        if block:
            self._db.insert_log("safety", "blocked", block)
            return f"Iris: {block}"

        if self.ctx.step == DialogueStep.MONITOR_WAIT_APPROVAL and self.ctx.pending_monitor:
            return self._handle_monitor_approval(text)

        # 멀티턴: 질문 단계 후속 입력
        if self.ctx.step == DialogueStep.WORK_ASK_TASK:
            return self._continue_work_flow(text)
        if self.ctx.step == DialogueStep.GAME_ASK_TITLE:
            return self._continue_game_flow(text)
        if self.ctx.step == DialogueStep.CREATIVE_ASK_TYPE:
            return self._continue_creative_flow(text)

        # 승인 대기 중
        if self.ctx.step in (
            DialogueStep.WORK_WAIT_APPROVAL,
            DialogueStep.GAME_WAIT_APPROVAL,
            DialogueStep.CREATIVE_WAIT_APPROVAL,
        ):
            return self._handle_pending_approval(text)

        kind = classify_command(text)

        if kind is CommandKind.WORK_MODE:
            return self._start_work_flow(text)

        if kind is CommandKind.GAME_MODE:
            return self._start_game_flow(text)

        if kind is CommandKind.CREATIVE_MODE:
            return self._start_creative_flow(text)

        if kind is CommandKind.MONITORING_STATUS:
            return "Iris: 모니터링 대시보드와 알림 패널에서 상태를 확인할 수 있습니다."

        if kind is CommandKind.ALERT_COMMAND:
            return "Iris: 알림 패널에서 확인해 주세요."

        if kind is CommandKind.COMPUTER_ACTION:
            return "Iris: 해당 조작은 안전 정책상 자동 실행하지 않습니다. 구체적 요청을 말씀해 주시고 승인 절차를 거쳐 주세요."

        # 일반 대화는 상위에서 LLM 호출로 처리
        return ""

    def _start_work_flow(self, text: str) -> str:
        self.ctx.step = DialogueStep.WORK_ASK_TASK
        recent = format_recent_work_suggestion(self._db)
        return work_mode.work_entry_message(recent)

    def _continue_work_flow(self, text: str) -> str:
        if self.ctx.step == DialogueStep.WORK_ASK_TASK:
            preset = work_mode.match_work_preset(text)
            self.ctx.pending = PendingPlan(
                title=preset.title,
                preset_id=preset.id,
                app_keys=list(preset.suggested_app_keys),
                work_type_label=preset.title,
            )
            self.ctx.step = DialogueStep.WORK_WAIT_APPROVAL
            return work_mode.propose_work_apps_message(preset)
        return ""

    def _start_game_flow(self, text: str) -> str:
        if re.search(r"(게임할래|게임\s*할래)", text, re.IGNORECASE):
            self.ctx.step = DialogueStep.GAME_ASK_TITLE
            return game_mode.game_entry_message()
        # 이미 게임 이름 포함
        preset = game_mode.match_game_preset(text)
        self.ctx.pending = PendingPlan(
            title=preset.title,
            preset_id=preset.id,
            app_keys=list(preset.suggested_app_keys),
            work_type_label="game",
        )
        self.ctx.step = DialogueStep.GAME_WAIT_APPROVAL
        return game_mode.propose_side_apps_message(preset)

    def _continue_game_flow(self, text: str) -> str:
        if self.ctx.step == DialogueStep.GAME_ASK_TITLE:
            preset = game_mode.match_game_preset(text)
            self.ctx.pending = PendingPlan(
                title=preset.title,
                preset_id=preset.id,
                app_keys=list(preset.suggested_app_keys),
                work_type_label="game",
            )
            self.ctx.step = DialogueStep.GAME_WAIT_APPROVAL
            return game_mode.propose_side_apps_message(preset)
        return ""

    def _start_creative_flow(self, text: str) -> str:
        self.ctx.step = DialogueStep.CREATIVE_ASK_TYPE
        return creative_mode.creative_entry_message()

    def _continue_creative_flow(self, text: str) -> str:
        if self.ctx.step == DialogueStep.CREATIVE_ASK_TYPE:
            preset = creative_mode.match_creative_preset(text)
            self.ctx.pending = PendingPlan(
                title=preset.title,
                preset_id=preset.id,
                app_keys=list(preset.suggested_app_keys),
                work_type_label="creative",
            )
            self.ctx.step = DialogueStep.CREATIVE_WAIT_APPROVAL
            return creative_mode.propose_creative_apps_message(preset)
        return ""

    def _handle_pending_approval(self, text: str) -> str:
        if _is_reject(text):
            self.ctx.clear()
            return "Iris: 실행을 취소했습니다."
        if not _is_approval(text):
            return "Iris: 실행하려면 '응' 또는 '승인' 이라고 말씀해 주세요. 취소는 '취소' 입니다."

        pending = self.ctx.pending
        self.ctx.clear()
        if not pending:
            return "Iris: 실행할 계획이 없습니다."

        preset = find_preset(pending.preset_id)
        if not preset:
            return "Iris: 프리셋을 찾을 수 없습니다."
        plan = plan_from_preset(preset)
        msg = self._executor.execute_plan(plan, preset, approved=True)
        self._db.insert_log("execute", pending.title, msg)
        return "Iris: 승인 확인. 요청한 환경을 실행합니다.\n" + msg

    def _handle_monitor_approval(self, text: str) -> str:
        """모니터링에서 제안한 키보드 입력 — 사용자 승인 후에만 실행."""
        pm = self.ctx.pending_monitor
        if not pm:
            self.ctx.clear()
            return "Iris: 대기 중인 모니터링 동작이 없습니다."

        if _is_reject(text):
            self.ctx.clear()
            self._db.insert_log("monitor", "user_reject", f"event={pm.event_id}")
            return "Iris: 모니터링 제안 실행을 취소했습니다."

        if not _is_approval(text):
            return "Iris: 실행하려면 '응' 또는 '승인' 이라고 말씀해 주세요. 취소는 '취소' 입니다."

        from iris.automation import keyboard_mouse_controller, window_controller

        self.ctx.clear()
        ok_focus, reason_f = window_controller.focus_and_place(pm.focus_hint, 40, 40, 1100, 720)
        if not ok_focus:
            self._db.insert_log("monitor", "focus_fail", reason_f)

        keys = (pm.suggested_input or "y").strip() or "y"
        ok_type, reason_t = keyboard_mouse_controller.type_text_approved(keys, approved=True)
        self._db.insert_monitoring_action(
            "keyboard_type",
            True,
            f"focus={reason_f}; type={reason_t}",
            target_id=pm.target_id,
            command=keys,
        )
        self._db.update_event_user_flags(pm.event_id, True, ok_type)
        self._db.insert_log("monitor", "approved_action", f"target={pm.target_id} ok={ok_type}")
        if ok_type:
            return f"Iris: 승인에 따라 '{keys}' 입력을 시도했습니다."
        return f"Iris: 승인은 기록했으나 입력 실패: {reason_t}"
