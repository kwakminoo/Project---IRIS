"""Iris 대화·모드·실행 오케스트레이션."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Dict, Sequence

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.prompt_builder import build_messages
from iris.assistant.llm_approval import FollowupDecision, resolve_followup_for_pending
from iris.assistant.safety_guard import quick_block_user_text
from iris.assistant.task_planner import plan_from_preset
from iris.automation.action_executor import ActionExecutor, IrisExecutionRequest
from iris.config.app_index import display_name_for_key, resolve_app_for_goal
from iris.config.preset_modes import PresetCategory, find_preset
from iris.core.command_router import CommandKind, classify_command
from iris.core.context_manager import (
    DialogueContext,
    DialogueStep,
    PendingAutomationTool,
    PendingComputerUseGoal,
    PendingMonitoringAction,
    PendingPlan,
    PendingUserAction,
)
from iris.core.recent_work_manager import format_recent_work_suggestion, seed_demo_recent_work
from iris.memory.memory_manager import MemoryManager
from iris.modes import creative_mode, game_mode, work_mode
from iris.storage.database import Database


# deprecated: Unified Router slots 없을 때 offline fallback용 regex hint
_APP_HINT_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"메모장|notepad", re.IGNORECASE), "notepad", "메모장"),
    (re.compile(r"커서|\bCursor\b", re.IGNORECASE), "code", "Cursor"),
    (re.compile(r"크롬|\bChrome\b", re.IGNORECASE), "chrome", "Chrome"),
    (re.compile(r"엣지|\bEdge\b", re.IGNORECASE), "edge", "Edge"),
    (re.compile(r"디스코드|\bDiscord\b", re.IGNORECASE), "discord", "Discord"),
    (re.compile(r"파이썬|\bPython\b", re.IGNORECASE), "python", "Python"),
    (re.compile(r"스팀|\bSteam\b", re.IGNORECASE), "steam", "Steam"),
    (re.compile(r"롤|리그|\bLeague\b", re.IGNORECASE), "league", "League of Legends"),
    (re.compile(r"\bOBS\b|옵스", re.IGNORECASE), "obs", "OBS"),
]


def _resolve_launch_target(
    text: str,
    app_paths: Dict[str, str] | None = None,
    db: Database | None = None,
    *,
    slots: dict | None = None,
) -> tuple[str | None, str | None]:
    """(app_key, 표시 이름). Router slots.app_key가 있으면 Tier1, regex는 offline fallback만."""
    if slots:
        key = str(slots.get("app_key") or "").strip()
        if key:
            disp = str(slots.get("display_name") or "").strip() or display_name_for_key(key, db)
            return key, disp
        return None, None
    for pat, key, disp in _APP_HINT_PATTERNS:
        if pat.search(text):
            return key, disp
    if app_paths:
        key, _ = resolve_app_for_goal(text, app_paths, db=db)
        if key:
            return key, display_name_for_key(key, db)
    return None, None


class IrisAssistant:
    """텍스트/음성 공통 처리."""

    def __init__(
        self,
        db: Database,
        executor: ActionExecutor,
        gemma: GemmaClient,
        app_paths: Dict[str, str],
        settings: object | None = None,
    ) -> None:
        self._db = db
        self._executor = executor
        self._gemma = gemma
        self._app_paths = app_paths
        self._settings = settings
        self.ctx = DialogueContext()
        self.memory = MemoryManager(db)
        seed_demo_recent_work(db)
        self._task_runtime_bundle = None
        self._cu_task_adapter = None

    def _ensure_task_runtime(self) -> object | None:
        """Task Runtime 서비스·Adapter lazy 초기화."""
        if self._cu_task_adapter is not None:
            return self._cu_task_adapter
        import logging
        import os

        from iris.application.task_runtime_health import get_task_runtime_health

        logger = logging.getLogger("iris.task_runtime")
        health = get_task_runtime_health()
        try:
            from iris.application.runtime_factory import build_task_runtime
            from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter

            self._task_runtime_bundle = build_task_runtime(
                self._db, self._executor.tool_registry
            )
            self._cu_task_adapter = CuTaskAdapter(self._task_runtime_bundle)
            from iris.infrastructure.events.task_status_bridge import TaskStatusEventBridge

            self._task_runtime_bundle.events.subscribe(TaskStatusEventBridge())
            return self._cu_task_adapter
        except Exception as exc:
            logger.exception("Task Runtime initialization failed")
            health.mark_failed(exc)
            self._db.insert_log(
                "task_runtime",
                "init_failed",
                f"{type(exc).__name__}: {exc}"[:500],
            )
            if os.environ.get("IRIS_STRICT_TASK_RUNTIME") == "1":
                raise
            return None

    @property
    def task_runtime_health(self):
        from iris.application.task_runtime_health import get_task_runtime_health

        return get_task_runtime_health()

    def _create_computer_use_agent(self) -> object:
        from iris.assistant.computer_use_agent import ComputerUseAgent

        return ComputerUseAgent(
            self,
            self._gemma,
            self._executor.tool_registry,
            max_steps=20,
            task_runtime=self._ensure_task_runtime(),
        )

    def update_app_paths(self, app_paths: Dict[str, str]) -> None:
        """앱 인덱스 병합 후 경로 dict 갱신."""
        self._app_paths.clear()
        self._app_paths.update(app_paths)

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
        mem = self.memory.build_extra_context()
        hist = list(history) if history is not None else self.memory.short_term_history()
        return build_messages(
            user_text,
            extra_context=extra_context,
            history=hist,
            memory_context=mem or None,
        )

    def run_agent_loop(self, text: str, *, routed: CommandKind | None = None) -> str:
        """JSON 계획 → 도구 실행 → observation 요약 Agent loop."""
        from iris.assistant.orchestrator import AgentOrchestrator

        if not hasattr(self, "_agent_orchestrator"):
            self._agent_orchestrator = AgentOrchestrator(self._db, self, self._gemma)
        return self._agent_orchestrator.run(text, intent=routed)

    def run_pending_cu_tool(
        self,
        tool_name: str,
        params: dict,
        *,
        summary: str = "",
    ) -> str:
        """승인된 CRITICAL 도구 1스텝만 실행 (레거시·테스트용)."""
        from iris.assistant.computer_use_agent import (
            ComputerUseAgent,
            format_pending_tool_user_message,
        )
        from iris.config.app_index import display_name_for_key

        if not hasattr(self, "_computer_use_agent"):
            self._computer_use_agent = ComputerUseAgent(
                self,
                self._gemma,
                self._executor.tool_registry,
                max_steps=20,
            )
        disp = ""
        if tool_name == "launch_app":
            key = str(params.get("app_key") or "")
            disp = str(params.get("display_name") or display_name_for_key(key, self._db))
        result = self._computer_use_agent.run_pending_tool(
            tool_name,
            params,
            summary=summary,
            approved=True,
        )
        return format_pending_tool_user_message(tool_name, result, disp)

    def run_computer_use_resume(
        self,
        pending: PendingComputerUseGoal,
        *,
        on_user_notify: Callable[[str], None] | None = None,
    ) -> str:
        """CRITICAL 승인 후 CU 루프 재개 — checkpoint verify 후 루프 계속."""
        from iris.assistant.computer_use_agent import ComputerUseAgent

        if not hasattr(self, "_computer_use_agent"):
            self._computer_use_agent = self._create_computer_use_agent()
        body = self._computer_use_agent.resume_after_critical_approval(
            pending,
            on_user_notify=on_user_notify,
        )
        if body.startswith("Iris:"):
            return body
        return f"Iris: {body}"

    def run_computer_use_loop(
        self,
        text: str,
        *,
        goal: str | None = None,
        slots: dict | None = None,
        routed: CommandKind | None = None,
        on_user_notify: Callable[[str], None] | None = None,
    ) -> str:
        """Perceive → Plan → Act → Verify multi-step Computer Use 루프 (음성·텍스트 공용)."""
        from iris.assistant.computer_use_agent import ComputerUseAgent

        _ = routed  # 분류는 TurnCoordinator·LLM Intent Router에서 완료
        cu_goal = (goal or text).strip()
        if not hasattr(self, "_computer_use_agent"):
            self._computer_use_agent = self._create_computer_use_agent()
        body = self._computer_use_agent.run(
            cu_goal, slots=slots, on_user_notify=on_user_notify
        )
        if body.startswith("Iris:"):
            return body
        return f"Iris: {body}"

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
        self.ctx.pending_automation = None
        self.ctx.pending_monitor = pending
        self.ctx.step = DialogueStep.MONITOR_WAIT_APPROVAL
        return True

    def handle_user_text(
        self,
        text: str,
        *,
        routed: CommandKind | None = None,
        llm_preset_id: str | None = None,
    ) -> str:
        """사용자 입력 한 턴 처리.

        routed:
            Intent Router에서 이미 분류한 경우 전달해 중복 휴리스틱을 피한다.
        llm_preset_id:
            Phase 3 — 멀티턴 질문에 대한 답에서 Gemma가 고른 preset_id (검증 후 사용).
        """
        block = quick_block_user_text(text)
        if block:
            self._db.insert_log("safety", "blocked", block)
            return f"Iris: {block}"

        if self.ctx.step == DialogueStep.MONITOR_WAIT_APPROVAL and self.ctx.pending_monitor:
            return self._handle_monitor_approval(text)

        if self.ctx.step == DialogueStep.ACTION_WAIT_APPROVAL and self.ctx.pending_automation:
            return self._handle_automation_approval(text)

        # 멀티턴: 질문 단계 후속 입력
        if self.ctx.step == DialogueStep.WORK_ASK_TASK:
            return self._continue_work_flow(text, llm_preset_id=llm_preset_id)
        if self.ctx.step == DialogueStep.GAME_ASK_TITLE:
            return self._continue_game_flow(text, llm_preset_id=llm_preset_id)
        if self.ctx.step == DialogueStep.CREATIVE_ASK_TYPE:
            return self._continue_creative_flow(text, llm_preset_id=llm_preset_id)

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
            return self.monitoring_status_reply()

        if kind is CommandKind.GET_SYSTEM_INFO:
            return self.request_automation_tool(
                "get_system_info",
                {},
                "시스템 사양·리소스 요약",
                settings=self._settings,
            )

        if kind is CommandKind.OPEN_URL:
            from iris.assistant.router_policy import detect_open_url

            url = detect_open_url(text)
            if not url:
                return "Iris: 열 URL을 찾지 못했습니다."
            return self.request_automation_tool(
                "open_url",
                {"url": url},
                f"URL 열기: {url}",
                settings=self._settings,
            )

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

    def _llm_approval_enabled(self) -> bool:
        settings = self._settings
        if settings is None:
            return True
        return bool(getattr(settings, "llm_approval_enabled", True))

    def _classify_approval_followup(
        self, text: str, context_prompt: str, *, force_rule_only: bool
    ) -> FollowupDecision:
        cls = resolve_followup_for_pending(
            text,
            context_prompt,
            self._gemma,
            force_rule_only=force_rule_only,
            use_llm=self._llm_approval_enabled(),
        )
        return cls.decision

    def _automation_tool_is_critical(self, tool_name: str) -> bool:
        from iris.automation.tool_types import RiskLevel

        tool = self._executor.tool_registry.get(tool_name)
        return tool is not None and tool.risk_level is RiskLevel.CRITICAL_RISK

    def monitoring_status_reply(self) -> str:
        """MonitorManager·DB와 연계된 요약 (오케스트레이터·UI 공용)."""
        return self._monitoring_status_reply()

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

    def request_automation_tool(
        self,
        tool_name: str,
        params: dict,
        summary: str,
        *,
        settings: object | None = None,
    ) -> str:
        """AutomationToolRegistry — LOW_RISK+설정 시 즉시 실행, 아니면 승인 대기."""
        from iris.automation.tool_types import AutomationToolContext

        eff_settings = settings if settings is not None else self._settings
        ctx = AutomationToolContext(
            params=params,
            approved=False,
            auto_approve_low_risk=self._db.get_auto_approve_low_risk(),
            app_paths=self._app_paths,
            settings=eff_settings,
            summary=summary,
        )
        reg = self._executor.tool_registry
        preview = reg.preview(tool_name, ctx)
        if not reg.needs_approval(tool_name, ctx):
            msg = self._executor.run_automation_tool(
                tool_name, params, approved=True, summary=summary, settings=eff_settings
            )
            self.memory.save_task_session(
                summary[:200],
                tools_run=[tool_name],
                observations=[msg[:200]],
            )
            return f"Iris: {msg}"

        self.ctx.pending = None
        self.ctx.pending_action = None
        self.ctx.pending_automation = PendingAutomationTool(
            tool_name=tool_name,
            params=params,
            summary=summary,
            preview=preview,
        )
        self.ctx.step = DialogueStep.ACTION_WAIT_APPROVAL
        return f"Iris: {preview}\n실행할까요? ('응' / '승인' 또는 '취소')"

    def _handle_automation_approval(self, text: str) -> str:
        pa = self.ctx.pending_automation
        if not pa:
            self.ctx.clear()
            return "Iris: 대기 중인 자동화 동작이 없습니다."
        force_rule = self._automation_tool_is_critical(pa.tool_name)
        decision = self._classify_approval_followup(
            text, pa.preview or pa.summary, force_rule_only=force_rule
        )
        if decision is FollowupDecision.REJECT:
            self.ctx.clear()
            self._db.insert_log("automation_tool", "reject", pa.summary)
            self.memory.save_task_session(
                pa.summary[:200], approvals=["rejected:" + pa.tool_name]
            )
            return "Iris: 자동화 실행을 취소했습니다."
        if decision is not FollowupDecision.APPROVE:
            return "Iris: 실행하려면 '응' 또는 '승인' 이라고 말씀해 주세요. 취소는 '취소' 입니다."

        self.ctx.clear()
        msg = self._executor.run_automation_tool(
            pa.tool_name,
            pa.params,
            approved=True,
            summary=pa.summary,
            settings=self._settings,
        )
        self.memory.save_task_session(
            pa.summary[:200],
            tools_run=[pa.tool_name],
            observations=[msg[:200]],
            approvals=["approved:" + pa.tool_name],
        )
        self._db.insert_log("automation_tool", "approved", f"{pa.tool_name}: {msg[:500]}")
        return f"Iris: 승인 확인. {msg}"

    def _bind_action_approval(self, pa: PendingUserAction, question: str) -> str:
        """단일 실행 승인 대기 상태로 전환."""
        self.ctx.pending = None
        self.ctx.pending_action = pa
        self.ctx.pending_automation = None
        self.ctx.step = DialogueStep.ACTION_WAIT_APPROVAL
        return f"Iris: {question}"

    def _execute_user_action_now(self, pa: PendingUserAction) -> str:
        """1~3단계 단일 실행은 승인 대기 없이 바로 실행한다."""
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
        return "Iris: 요청을 실행합니다.\n" + msg

    def _execute_preset_now(self, pending: PendingPlan) -> str:
        """모드 프리셋 실행도 현재 정책상 3단계 이하로 보고 바로 실행한다."""
        preset = find_preset(pending.preset_id)
        if not preset:
            return "Iris: 프리셋을 찾을 수 없습니다."
        plan = plan_from_preset(preset)
        msg = self._executor.execute_plan(plan, preset, approved=True)
        self._db.insert_log("execute", pending.title, msg)
        self.memory.save_task_session(
            pending.title[:200],
            tools_run=[f"preset:{pending.preset_id}"],
            observations=[msg[:200]],
        )
        self.ctx.clear()
        return "Iris: 요청한 환경을 실행합니다.\n" + msg

    def launch_app_by_key(
        self,
        app_key: str,
        *,
        display_name: str = "",
        user_text: str = "",
    ) -> str:
        """Unified Router slots.app_key — LLM 우선, 휴리스틱 재해석 생략."""
        key = app_key.strip()
        if not key:
            return self._start_app_launch_flow(user_text or app_key)
        disp = display_name.strip() or display_name_for_key(key, self._db)
        summary = f"앱 실행 요청: {disp} ({key})"
        pa = PendingUserAction(
            command_kind=CommandKind.APP_LAUNCH,
            summary=summary,
            user_original_text=user_text or summary,
            app_key=key,
            display_name=disp,
        )
        return self._execute_user_action_now(pa)

    def _start_app_launch_flow(self, text: str) -> str:
        app_key, display = _resolve_launch_target(text, self._app_paths, self._db)
        if not app_key:
            return "Iris: 어떤 앱을 실행할지 파악하지 못했습니다. 예: Cursor, Chrome, Edge, 메모장."
        return self.launch_app_by_key(
            app_key, display_name=display or "", user_text=text
        )

    def _start_window_control_flow(self, text: str) -> str:
        summary = f"창 제어 요청: {text.strip()[:200]}"
        pa = PendingUserAction(
            command_kind=CommandKind.WINDOW_CONTROL,
            summary=summary,
            user_original_text=text,
        )
        return self._execute_user_action_now(pa)

    def _start_file_task_flow(self, text: str) -> str:
        summary = f"파일 작업 요청: {text.strip()[:200]}"
        pa = PendingUserAction(
            command_kind=CommandKind.FILE_TASK,
            summary=summary,
            user_original_text=text,
        )
        return self._execute_user_action_now(pa)

    def _start_complex_automation_flow(self, text: str) -> str:
        summary = f"복잡 자동화 요청: {text.strip()[:200]}"
        pa = PendingUserAction(
            command_kind=CommandKind.COMPLEX_AUTOMATION,
            summary=summary,
            user_original_text=text,
        )
        return self._execute_user_action_now(pa)

    def _start_work_flow(self, text: str) -> str:
        self.ctx.pending_action = None
        self.ctx.step = DialogueStep.WORK_ASK_TASK
        recent = format_recent_work_suggestion(self._db)
        return work_mode.work_entry_message(recent)

    def _continue_work_flow(
        self, text: str, *, llm_preset_id: str | None = None
    ) -> str:
        if self.ctx.step == DialogueStep.WORK_ASK_TASK:
            # Phase 3: TurnCoordinator가 넘긴 preset_id 우선, 없으면 regex 매칭
            preset = None
            if llm_preset_id:
                cand = find_preset(llm_preset_id)
                if cand is not None and cand.category == PresetCategory.WORK:
                    preset = cand
            if preset is None:
                preset = work_mode.match_work_preset(text)
            self.ctx.pending_action = None
            self.ctx.pending = PendingPlan(
                title=preset.title,
                preset_id=preset.id,
                app_keys=list(preset.suggested_app_keys),
                work_type_label=preset.title,
            )
            return self._execute_preset_now(self.ctx.pending)
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
        return self._execute_preset_now(self.ctx.pending)

    def _continue_game_flow(
        self, text: str, *, llm_preset_id: str | None = None
    ) -> str:
        if self.ctx.step == DialogueStep.GAME_ASK_TITLE:
            preset = None
            if llm_preset_id:
                cand = find_preset(llm_preset_id)
                if cand is not None and cand.category == PresetCategory.GAME:
                    preset = cand
            if preset is None:
                preset = game_mode.match_game_preset(text)
            self.ctx.pending_action = None
            self.ctx.pending = PendingPlan(
                title=preset.title,
                preset_id=preset.id,
                app_keys=list(preset.suggested_app_keys),
                work_type_label="game",
            )
            return self._execute_preset_now(self.ctx.pending)
        return ""

    def _start_creative_flow(self, text: str) -> str:
        self.ctx.pending_action = None
        self.ctx.step = DialogueStep.CREATIVE_ASK_TYPE
        return creative_mode.creative_entry_message()

    def _continue_creative_flow(
        self, text: str, *, llm_preset_id: str | None = None
    ) -> str:
        if self.ctx.step == DialogueStep.CREATIVE_ASK_TYPE:
            preset = None
            if llm_preset_id:
                cand = find_preset(llm_preset_id)
                if cand is not None and cand.category == PresetCategory.CREATIVE:
                    preset = cand
            if preset is None:
                preset = creative_mode.match_creative_preset(text)
            self.ctx.pending_action = None
            self.ctx.pending = PendingPlan(
                title=preset.title,
                preset_id=preset.id,
                app_keys=list(preset.suggested_app_keys),
                work_type_label="creative",
            )
            return self._execute_preset_now(self.ctx.pending)
        return ""

    def _handle_pending_approval(self, text: str) -> str:
        ctx_prompt = ""
        if self.ctx.pending_action:
            ctx_prompt = self.ctx.pending_action.summary
        elif self.ctx.pending:
            ctx_prompt = self.ctx.pending.title
        decision = self._classify_approval_followup(text, ctx_prompt, force_rule_only=False)
        if decision is FollowupDecision.REJECT:
            self.ctx.clear()
            return "Iris: 실행을 취소했습니다."
        if decision is not FollowupDecision.APPROVE:
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
        self.memory.save_task_session(
            pending.title[:200],
            tools_run=[f"preset:{pending.preset_id}"],
            observations=[msg[:200]],
        )
        return "Iris: 승인 확인. 요청한 환경을 실행합니다.\n" + msg

    def _handle_monitor_approval(self, text: str) -> str:
        """모니터링에서 제안한 키보드 입력 — 사용자 승인 후에만 실행."""
        pm = self.ctx.pending_monitor
        if not pm:
            self.ctx.clear()
            return "Iris: 대기 중인 모니터링 동작이 없습니다."

        decision = self._classify_approval_followup(
            text, pm.natural_language or pm.suggested_input, force_rule_only=False
        )
        if decision is FollowupDecision.REJECT:
            self.ctx.clear()
            self._db.insert_log("monitor", "user_reject", f"event={pm.event_id}")
            return "Iris: 모니터링 제안 실행을 취소했습니다."

        if decision is not FollowupDecision.APPROVE:
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
