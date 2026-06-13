"""텍스트 입력 고정 단계 플로우 — 메모장 등 compose_text 스킬 (PAV 플래너 우회)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from iris.assistant.computer_use_agent import ComputerUseContext, USER_QUESTION_PREFIX
from iris.assistant.cu_mechanical_verify import mechanical_verify_checkpoint
from iris.assistant.cu_perception import PerceptionObservation
from iris.assistant.execution_tier_policy import input_conflict_message, is_input_conflict_tool
from iris.assistant.tool_user_reply import format_pending_tool_user_message
from iris.automation.tool_types import AutomationToolResult
from iris.config.app_index import display_name_for_key
from iris.core.activity_sink import push_activity_line

if TYPE_CHECKING:
    from iris.assistant.computer_use_agent import ComputerUseAgent

_MAX_TYPE_REPAIR = 2


@dataclass
class _ComposeCtx:
    """스킬 플로우 세션 — mechanical verify용 최소 CU 컨텍스트."""

    goal: str
    slots: dict[str, Any]
    last_focus_hwnd: int = 0
    last_type_verify: bool | None = None
    last_perception: PerceptionObservation | None = None
    observations: list[str] = field(default_factory=list)


def should_run_text_compose(slots: dict[str, Any] | None) -> bool:
    """Router task_type/skill_id로 TextCompose 진입 여부."""
    if not slots:
        return False
    from iris.assistant.action_skills import resolve_skill_id

    return resolve_skill_id(slots) == "text_compose"


class TextComposeFlow:
    """앱 포커스 → type_text → cp_text_typed 기계 검증 (Repair 최대 2회, LLM 없음)."""

    def __init__(self, cu_agent: ComputerUseAgent) -> None:
        self._agent = cu_agent
        self._assistant = cu_agent._assistant

    def run(self, goal: str, slots: dict[str, Any]) -> str:
        goal = goal.strip()
        app_key = str(slots.get("app_key") or "").strip()
        text = str(slots.get("text_to_type") or "").strip()

        if not app_key:
            return f"{USER_QUESTION_PREFIX} 어느 앱에 입력할까요? (예: 메모장)"
        if not text:
            return f"{USER_QUESTION_PREFIX} 어떤 내용을 입력할까요?"

        db = self._assistant._db
        display_name = str(slots.get("display_name") or "").strip()
        if not display_name:
            display_name = display_name_for_key(app_key, db)
        title_sub = display_name or app_key
        flow_slots = {
            **slots,
            "app_key": app_key,
            "display_name": display_name,
            "text_to_type": text,
            "task_type": "compose_text",
        }

        db.insert_log("text_compose_flow", "start", f"{app_key} len={len(text)}")
        push_activity_line(f"TextComposeFlow: start app={app_key}")
        ctx = _ComposeCtx(goal=goal, slots=flow_slots)

        # 1. list_open_windows + perceive — 앱 창 존재 확인
        self._perceive(ctx, reason="compose_check_app")
        open_mech = mechanical_verify_checkpoint(
            "cp_app_open",
            perception=ctx.last_perception,
            slots=flow_slots,
            executed_plans=(),
            cu_ctx=ctx,
        )
        if open_mech.status == "failed":
            launch_res = self._run_tool(
                "launch_app",
                {"app_key": app_key, "display_name": display_name},
                summary=f"compose launch {display_name}",
            )
            if not launch_res.success:
                return format_pending_tool_user_message("launch_app", launch_res, display_name)
            self._perceive(ctx, reason="compose_after_launch")

        # 3. focus_window
        focus_res = self._run_tool(
            "focus_window",
            {"title_sub": title_sub},
            summary=f"compose focus {title_sub[:24]}",
        )
        if focus_res.success:
            self._update_focus_hwnd(ctx, title_sub)
        focus_mech = mechanical_verify_checkpoint(
            "cp_focus",
            perception=ctx.last_perception,
            slots=flow_slots,
            executed_plans=(),
            cu_ctx=ctx,
        )
        if focus_mech.status == "failed" and not focus_res.success:
            return (
                f"요청하신 작업을 실행하지 못했습니다. "
                f"{display_name} 창에 포커스하지 못했습니다."
            )

        # 4. (선택) uia_snapshot
        self._run_tool(
            "uia_snapshot",
            {"window_title_sub": title_sub},
            summary="compose uia_snapshot",
        )

        # 5–7. type_text + cp_text_typed (Repair 최대 2회)
        verify_status = "failed"
        last_type_res: AutomationToolResult | None = None
        for attempt in range(_MAX_TYPE_REPAIR + 1):
            if attempt > 0:
                push_activity_line(f"TextComposeFlow: repair attempt={attempt}")
                self._run_tool(
                    "focus_window",
                    {"title_sub": title_sub},
                    summary="compose repair focus",
                )
                self._update_focus_hwnd(ctx, title_sub)
                self._clear_input_field()

            self._notify_input_conflict("type_text", {"text": text})
            last_type_res = self._run_tool(
                "type_text",
                {"text": text},
                summary=f"compose type {text[:24]}",
            )
            detail = str(last_type_res.detail or "")
            if last_type_res.success and "|verified" in detail:
                ctx.last_type_verify = True
            elif last_type_res.success:
                ctx.last_type_verify = None
            else:
                ctx.last_type_verify = False

            self._perceive(ctx, reason="compose_after_type")
            type_mech = mechanical_verify_checkpoint(
                "cp_text_typed",
                perception=ctx.last_perception,
                slots=flow_slots,
                executed_plans=(),
                cu_ctx=ctx,
            )
            verify_status = type_mech.status
            if type_mech.status == "success":
                break

        if verify_status == "success" and last_type_res is not None:
            msg = format_pending_tool_user_message(
                "type_text",
                last_type_res,
                f"{display_name}에 입력",
            )
            db.insert_log("text_compose_flow", "complete", msg[:200])
            self._assistant.memory.save_task_session(
                goal[:200],
                tools_run=["launch_app", "focus_window", "type_text"],
                observations=[f"text={text[:80]}"],
            )
            return msg

        reason = "입력 내용을 화면에서 확인하지 못했습니다."
        if last_type_res and not last_type_res.success:
            reason = last_type_res.message or reason
        db.insert_log("text_compose_flow", "verify_fail", reason[:200])
        return f"요청하신 작업을 실행하지 못했습니다. {reason}"

    def _perceive(self, ctx: _ComposeCtx, *, reason: str) -> None:
        """ComputerUseAgent._run_perceive_desktop 위임."""
        cu_ctx = ComputerUseContext(
            goal=ctx.goal,
            slots=ctx.slots,
            last_focus_hwnd=ctx.last_focus_hwnd,
            observations=list(ctx.observations),
        )
        cu_ctx.last_type_verify = ctx.last_type_verify
        self._agent._run_perceive_desktop(cu_ctx, reason=reason)
        ctx.last_perception = cu_ctx.last_perception
        ctx.observations = list(cu_ctx.observations)

    def _update_focus_hwnd(self, ctx: _ComposeCtx, title_sub: str) -> None:
        from iris.automation import window_controller

        wins = window_controller.find_windows_by_title_substring(title_sub)
        if wins and wins[0].hwnd > 0:
            ctx.last_focus_hwnd = wins[0].hwnd

    def _notify_input_conflict(self, tool_name: str, params: dict[str, Any]) -> None:
        if not is_input_conflict_tool(tool_name):
            return
        announce = input_conflict_message(tool_name, params)
        push_activity_line(f"TextComposeFlow: input_conflict — {announce[:80]}")
        notify = getattr(self._agent, "_on_user_notify", None)
        if notify is not None:
            notify(announce)
            delay = float(getattr(self._agent, "_input_notify_delay", 2.0) or 2.0)
            time.sleep(max(0.5, min(delay, 8.0)))

    @staticmethod
    def _clear_input_field() -> None:
        from iris.automation.text_input_controller import _clear_focused_field

        _clear_focused_field()

    def _run_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        summary: str,
    ) -> AutomationToolResult:
        return self._agent.run_tool_recorded(
            tool_name,
            params,
            summary=summary[:200],
            approved=True,
        )
