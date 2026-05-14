"""Iris 대화·모드·실행 오케스트레이션."""

from __future__ import annotations

import re
from typing import Dict, Sequence

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.prompt_builder import build_messages
from iris.assistant.safety_guard import quick_block_user_text
from iris.assistant.task_planner import plan_from_preset
from iris.automation.action_executor import ActionExecutor, IrisExecutionRequest
from iris.config.preset_modes import find_preset
from iris.core.command_router import CommandKind, classify_command
from iris.core.context_manager import (
    DialogueContext,
    DialogueStep,
    PendingMonitoringAction,
    PendingPlan,
    PendingUserAction,
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


_LAUNCH_SPECS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"커서|\bCursor\b", re.IGNORECASE), "code", "Cursor"),
    (re.compile(r"크롬|\bChrome\b", re.IGNORECASE), "chrome", "Chrome"),
    (re.compile(r"엣지|\bEdge\b", re.IGNORECASE), "edge", "Edge"),
    (re.compile(r"디스코드|\bDiscord\b", re.IGNORECASE), "discord", "Discord"),
    (re.compile(r"파이썬|\bPython\b", re.IGNORECASE), "python", "Python"),
    (re.compile(r"\bSteam\b", re.IGNORECASE), "steam", "Steam"),
    (re.compile(r"롤|리그|\bLeague\b", re.IGNORECASE), "league", "League of Legends"),
    (re.compile(r"\bOBS\b|옵스", re.IGNORECASE), "obs", "OBS"),
]


def _resolve_launch_target(text: str) -> tuple[str | None, str | None]:
    """(app_key, 표시 이름). 경로 유무와 무관하게 의도 키를 추출."""
    for pat, key, disp in _LAUNCH_SPECS:
        if pat.search(text):
            return key, disp
    return None, None


class IrisAssistant:
    """텍스트/음성 공통 처리."""

    def __init__(
        self,
        db: Database,
        executor: ActionExecutor,
        gemma: GemmaClient,
        app_paths: Dict[str, str],
    ) -> None:
        self._db = db
        self._executor = executor
        self._gemma = gemma
        self._app_paths = app_paths
        self.ctx = DialogueContext()
        seed_demo_recent_work(db)

    @property
    def gemma_client(self) -> GemmaClient:
        """로컬 LLM 클라이언트 (UI·워커는 직접 Ollama URL을 쓰지 않고 이 인스턴스로 호출)."""
        return self._gemma

    def build_general_chat_messages(
        self,
        user_text: str,
        *,
        history: Sequence[ChatMessage] | None = None,
        extra_context: str | None = None,
    ) -> list[ChatMessage]:
        """시스템 프롬프트가 포함된 LLM 메시지 조립 (Ollama 호출 전 단계)."""
        return build_messages(user_text, extra_context=extra_context, history=history)

    def set_monitor_pending(self, pending: PendingMonitoringAction) -> bool:
        """모니터링 승인 대기. 작업/게임/단일 액션 승인 대기 중이면 True 반환하지 않고 스킵."""
        if self.ctx.step in (
            DialogueStep.WORK_WAIT_APPROVAL,
            DialogueStep.GAME_WAIT_APPROVAL,
            DialogueStep.CREATIVE_WAIT_APPROVAL,
            DialogueStep.ACTION_WAIT_APPROVAL,
        ):
            return False
        self.ctx.pending = None
        self.ctx.pending_action = None
        self.ctx.pending_monitor = pending
        self.ctx.step = DialogueStep.MONITOR_WAIT_APPROVAL
        return True

    def handle_user_text(self, text: str, *, routed: CommandKind | None = None) -> str:
        """사용자 입력 한 턴 처리.

        routed:
            Intent Router에서 이미 분류한 경우 전달해 중복 휴리스틱을 피한다.
        """
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

        # 승인 대기 중 (모드 플랜 + 단일 액션 공통)
        if self.ctx.step in (
            DialogueStep.WORK_WAIT_APPROVAL,
            DialogueStep.GAME_WAIT_APPROVAL,
            DialogueStep.CREATIVE_WAIT_APPROVAL,
            DialogueStep.ACTION_WAIT_APPROVAL,
        ):
            return self._handle_pending_approval(text)

        kind = routed if routed is not None else classify_command(text)

        if kind is CommandKind.WORK_MODE:
            return self._start_work_flow(text)

        if kind is CommandKind.GAME_MODE:
            return self._start_game_flow(text)

        if kind is CommandKind.CREATIVE_MODE:
            return self._start_creative_flow(text)

        if kind is CommandKind.MONITORING_STATUS:
            return self._monitoring_status_reply()

        if kind is CommandKind.COMPUTER_ACTION:
            return (
                "Iris: 해당 조작은 안전 정책상 자동 실행하지 않습니다. "
                "구체적 요청을 말씀해 주시고 승인 절차를 거쳐 주세요."
            )

        if kind is CommandKind.APP_LAUNCH:
            return self._start_app_launch_flow(text)

        if kind is CommandKind.WINDOW_CONTROL:
            return self._start_window_control_flow(text)

        if kind is CommandKind.FILE_TASK:
            return self._start_file_task_flow(text)

        if kind is CommandKind.COMPLEX_AUTOMATION:
            return self._start_complex_automation_flow(text)

        # 일반 대화는 상위에서 LLM 호출로 처리
        return ""

    def _monitoring_status_reply(self) -> str:
        """MonitorManager·DB와 연계된 요약 (UI 대시보드 보조)."""
        rows = self._db.list_targets(enabled_only=False)[:16]
        if not rows:
            return (
                "Iris: 등록된 모니터링 대상이 없습니다. "
                "오른쪽 대시보드에서 타깃을 추가하면 터미널·앱 상태를 추적할 수 있습니다."
            )
        lines: list[str] = ["Iris: 모니터링 상태 요약입니다.", ""]
        for row in rows:
            tid = int(row["id"])
            title = str(row["title"] or row["type"])
            last_ev = str(row["last_event"] or "").strip()
            st_db = str(row["status"] or "")
            rts = self._db.get_recent_target_state(tid)
            extra = ""
            if rts is not None:
                try:
                    extra = f" [감지: {rts['status']}]"
                except (KeyError, TypeError):
                    extra = ""
            ev = f" — 최근: {last_ev[:72]}…" if len(last_ev) > 72 else (f" — 최근: {last_ev}" if last_ev else "")
            lines.append(f"- {title} (DB상태 {st_db}){extra}{ev}")
        lines.append("")
        lines.append("상세 로그·알림은 오른쪽 모니터링 대시보드와 알림 패널을 확인해 주세요.")
        return "\n".join(lines)

    def _bind_action_approval(self, pa: PendingUserAction, question: str) -> str:
        """단일 실행 승인 대기 상태로 전환."""
        self.ctx.pending = None
        self.ctx.pending_action = pa
        self.ctx.step = DialogueStep.ACTION_WAIT_APPROVAL
        return f"Iris: {question}"

    def _start_app_launch_flow(self, text: str) -> str:
        app_key, display = _resolve_launch_target(text)
        if not app_key:
            return "Iris: 어떤 앱을 실행할지 파악하지 못했습니다. 예: Cursor, Chrome, Edge."

        if app_key not in self._app_paths:
            # 경로 없어도 보조 백엔드로 시도 가능 — 승인 후 실행 단계에서 처리
            pass

        summary = f"앱 실행 요청: {display} ({app_key})"
        pa = PendingUserAction(
            command_kind=CommandKind.APP_LAUNCH,
            summary=summary,
            user_original_text=text,
            app_key=app_key,
            display_name=display,
        )
        return self._bind_action_approval(pa, f"{display}를 실행할까요?")

    def _start_window_control_flow(self, text: str) -> str:
        summary = f"창 제어 요청: {text.strip()[:200]}"
        pa = PendingUserAction(
            command_kind=CommandKind.WINDOW_CONTROL,
            summary=summary,
            user_original_text=text,
        )
        return self._bind_action_approval(pa, "요청하신 창을 포커스하고 배치할까요?")

    def _start_file_task_flow(self, text: str) -> str:
        summary = f"파일 작업 요청: {text.strip()[:200]}"
        pa = PendingUserAction(
            command_kind=CommandKind.FILE_TASK,
            summary=summary,
            user_original_text=text,
        )
        return self._bind_action_approval(pa, "파일 검색·탐색을 진행할까요?")

    def _start_complex_automation_flow(self, text: str) -> str:
        summary = f"복잡 자동화 요청: {text.strip()[:200]}"
        pa = PendingUserAction(
            command_kind=CommandKind.COMPLEX_AUTOMATION,
            summary=summary,
            user_original_text=text,
        )
        return self._bind_action_approval(pa, "말씀하신 자동화를 실행할까요?")

    def _start_work_flow(self, text: str) -> str:
        self.ctx.pending_action = None
        self.ctx.step = DialogueStep.WORK_ASK_TASK
        recent = format_recent_work_suggestion(self._db)
        return work_mode.work_entry_message(recent)

    def _continue_work_flow(self, text: str) -> str:
        if self.ctx.step == DialogueStep.WORK_ASK_TASK:
            preset = work_mode.match_work_preset(text)
            self.ctx.pending_action = None
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
        self.ctx.pending_action = None
        if re.search(r"(게임할래|게임\s*할래)", text, re.IGNORECASE):
            self.ctx.step = DialogueStep.GAME_ASK_TITLE
            return game_mode.game_entry_message()
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
            self.ctx.pending_action = None
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
        self.ctx.pending_action = None
        self.ctx.step = DialogueStep.CREATIVE_ASK_TYPE
        return creative_mode.creative_entry_message()

    def _continue_creative_flow(self, text: str) -> str:
        if self.ctx.step == DialogueStep.CREATIVE_ASK_TYPE:
            preset = creative_mode.match_creative_preset(text)
            self.ctx.pending_action = None
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

        if self.ctx.step == DialogueStep.ACTION_WAIT_APPROVAL and self.ctx.pending_action:
            pa = self.ctx.pending_action
            self.ctx.clear()
            req = IrisExecutionRequest(
                command_kind=pa.command_kind,
                user_text=pa.user_original_text,
                summary=pa.summary,
                approved=True,
                app_key=pa.app_key,
                display_name=pa.display_name,
            )
            msg = self._executor.execute_iris_request(req)
            self._db.insert_log("execute", pa.summary, msg)
            return "Iris: 승인 확인. 요청을 실행합니다.\n" + msg

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
