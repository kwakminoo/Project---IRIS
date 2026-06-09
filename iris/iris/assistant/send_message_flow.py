"""메시지 전송 고정 단계 플로우 — 카톡·디스코드 send_message 스킬 (PAV 우회)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from iris.assistant.computer_use_agent import ComputerUseContext, USER_QUESTION_PREFIX
from iris.assistant.cu_checkpoint_verify import verify_checkpoint_hybrid
from iris.assistant.cu_mechanical_verify import mechanical_verify_checkpoint
from iris.assistant.execution_tier_policy import input_conflict_message, is_input_conflict_tool
from iris.assistant.tool_user_reply import format_pending_tool_user_message
from iris.automation.tool_types import AutomationToolResult
from iris.config.app_index import display_name_for_key
from iris.config.message_app_uia import MessageAppUiaProfile, profile_for_app
from iris.core.activity_sink import push_activity_line

if TYPE_CHECKING:
    from iris.assistant.computer_use_agent import ComputerUseAgent


@dataclass
class _SendCtx:
    """메시지 스킬 세션 — verify·Repair용."""

    goal: str
    slots: dict[str, Any]
    last_focus_hwnd: int = 0
    last_type_verify: bool | None = None
    last_perception: Any = None
    observations: list[str] = field(default_factory=list)


def should_run_send_message(slots: dict[str, Any] | None) -> bool:
    if not slots:
        return False
    from iris.assistant.action_skills import resolve_skill_id

    return resolve_skill_id(slots) == "send_message"


class SendMessageFlow:
    """launch/focus → (recipient) → 입력 → 전송 → cp_message_sent 검증."""

    def __init__(self, cu_agent: ComputerUseAgent) -> None:
        self._agent = cu_agent
        self._assistant = cu_agent._assistant
        self._gemma = cu_agent._gemma

    def run(self, goal: str, slots: dict[str, Any]) -> str:
        goal = goal.strip()
        app_key = str(slots.get("app_key") or "").strip()
        message_text = str(slots.get("message_text") or "").strip()
        recipient = str(slots.get("recipient") or "").strip()

        if not app_key:
            return f"{USER_QUESTION_PREFIX} 어느 앱으로 메시지를 보낼까요?"
        if not message_text:
            return f"{USER_QUESTION_PREFIX} 어떤 내용을 보낼까요?"

        db = self._assistant._db
        display_name = str(slots.get("display_name") or "").strip()
        if not display_name:
            display_name = display_name_for_key(app_key, db)
        profile = profile_for_app(app_key)
        title_sub = (profile.window_title_sub if profile else display_name) or app_key

        flow_slots = {
            **slots,
            "app_key": app_key,
            "display_name": display_name,
            "message_text": message_text,
            "task_type": "send_message",
        }
        if recipient:
            flow_slots["recipient"] = recipient

        db.insert_log("send_message_flow", "start", f"{app_key} len={len(message_text)}")
        push_activity_line(f"SendMessageFlow: start app={app_key}")
        ctx = _SendCtx(goal=goal, slots=flow_slots)

        # launch / focus
        self._perceive(ctx, reason="send_check_app")
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
                summary=f"send launch {display_name}",
            )
            if not launch_res.success:
                return format_pending_tool_user_message("launch_app", launch_res, display_name)

        focus_res = self._run_tool(
            "focus_window",
            {"title_sub": title_sub},
            summary=f"send focus {title_sub[:24]}",
        )
        if focus_res.success:
            self._update_focus_hwnd(ctx, title_sub)
        self._perceive(ctx, reason="send_after_focus")

        # 로그인·2FA UI 감지 → ask_user
        if self._detect_login_ui(ctx, profile):
            return (
                f"{USER_QUESTION_PREFIX} "
                f"{display_name}에 로그인이 필요해 보입니다. 로그인 후 다시 요청해 주세요."
            )

        # recipient 선택 (있으면 UIA, 없으면 현재 채팅창 가정)
        if recipient:
            if not self._select_recipient(ctx, profile, recipient, title_sub):
                if not recipient:
                    pass
                else:
                    return (
                        f"{USER_QUESTION_PREFIX} "
                        f"'{recipient}' 대화방을 찾지 못했습니다. "
                        "대화방을 직접 연 뒤 다시 요청해 주세요."
                    )
        elif self._focus_ambiguous(ctx, profile):
            return (
                f"{USER_QUESTION_PREFIX} "
                f"어느 대화방에 보낼지 알려주세요. (recipient 슬롯)"
            )

        # 입력창 UIA click → type_text
        self._click_input_field(profile, title_sub)
        self._notify_input_conflict("type_text", {"text": message_text})
        type_res = self._run_tool(
            "type_text",
            {"text": message_text},
            summary=f"send type {message_text[:24]}",
        )
        detail = str(type_res.detail or "")
        if type_res.success and "|verified" in detail:
            ctx.last_type_verify = True
        elif not type_res.success:
            ctx.last_type_verify = False
            return format_pending_tool_user_message("type_text", type_res)

        # 전송: uia_click(전송) 우선, else send_hotkey
        sent = self._send_message(profile, title_sub)
        if not sent.success:
            return format_pending_tool_user_message("uia_click", sent, "메시지 전송")

        self._perceive(ctx, reason="send_after_send")
        mech = mechanical_verify_checkpoint(
            "cp_message_sent",
            perception=ctx.last_perception,
            slots=flow_slots,
            executed_plans=(),
            cu_ctx=ctx,
        )
        if mech.status == "success":
            msg = format_pending_tool_user_message(
                "send_message",
                AutomationToolResult(True, f"{display_name}에 메시지를 보냈습니다."),
            )
            db.insert_log("send_message_flow", "complete", msg[:200])
            return msg

        if mech.status == "inconclusive":
            verify, _vision = verify_checkpoint_hybrid(
                self._gemma,
                goal=goal,
                plan_id="send_message_skill",
                checkpoint_id="cp_message_sent",
                executed_through_index=0,
                plans=(),
                observations=ctx.observations,
                slots=flow_slots,
                cu_ctx=ctx,
                last_perception=ctx.last_perception,
                max_attempts=1,
            )
            if verify and verify.achieved:
                msg = format_pending_tool_user_message(
                    "send_message",
                    AutomationToolResult(True, f"{display_name}에 메시지를 보냈습니다."),
                )
                db.insert_log("send_message_flow", "complete_llm", msg[:200])
                return msg

        db.insert_log("send_message_flow", "verify_fail", mech.gap[:200])
        return (
            "요청하신 작업을 실행하지 못했습니다. "
            "메시지 전송을 확인하지 못했습니다."
        )

    def _detect_login_ui(self, ctx: _SendCtx, profile: MessageAppUiaProfile | None) -> bool:
        """로그인·2FA UI 마커 — Safety ask_user."""
        markers = profile.login_ui_markers if profile else ("로그인", "Log In", "Login", "2FA")
        blob = ""
        if ctx.last_perception:
            blob = "\n".join(
                filter(
                    None,
                    [
                        ctx.last_perception.active_window_title,
                        ctx.last_perception.uia_snapshot_summary,
                        ctx.last_perception.scene_summary,
                        ctx.last_perception.open_windows_summary,
                    ],
                )
            ).lower()
        for m in markers:
            if m.lower() in blob:
                return True
        return False

    def _focus_ambiguous(self, ctx: _SendCtx, profile: MessageAppUiaProfile | None) -> bool:
        """포커스 대상이 메시지 앱이 아니면 recipient 질문."""
        if profile is None:
            return False
        active = (ctx.last_perception.active_window_title if ctx.last_perception else "") or ""
        if not active:
            return True
        sub = profile.window_title_sub.lower()
        return sub not in active.lower()

    def _select_recipient(
        self,
        ctx: _SendCtx,
        profile: MessageAppUiaProfile | None,
        recipient: str,
        title_sub: str,
    ) -> bool:
        """UIA로 대화방 검색·선택."""
        if profile and profile.recipient_search_edit_name:
            self._run_tool(
                "uia_click",
                {
                    "window_title_sub": title_sub,
                    "name": profile.recipient_search_edit_name,
                },
                summary="send recipient search",
            )
            self._notify_input_conflict("type_text", {"text": recipient})
            self._run_tool(
                "type_text",
                {"text": recipient},
                summary="send recipient query",
            )
        click_res = self._run_tool(
            "uia_click",
            {"window_title_sub": title_sub, "name": recipient},
            summary=f"send pick {recipient[:24]}",
        )
        if click_res.success:
            self._update_focus_hwnd(ctx, title_sub)
            return True
        return False

    def _click_input_field(
        self,
        profile: MessageAppUiaProfile | None,
        title_sub: str,
    ) -> None:
        if profile is None:
            return
        params: dict[str, Any] = {"window_title_sub": title_sub}
        if profile.input_field_automation_id:
            params["automation_id"] = profile.input_field_automation_id
        elif profile.input_field_name:
            params["name"] = profile.input_field_name
        else:
            return
        self._run_tool("uia_click", params, summary="send input focus")

    def _send_message(
        self,
        profile: MessageAppUiaProfile | None,
        title_sub: str,
    ) -> AutomationToolResult:
        if profile:
            if profile.send_button_automation_id:
                res = self._run_tool(
                    "uia_click",
                    {
                        "window_title_sub": title_sub,
                        "automation_id": profile.send_button_automation_id,
                    },
                    summary="send button click",
                )
                if res.success:
                    return res
            if profile.send_button_name:
                res = self._run_tool(
                    "uia_click",
                    {
                        "window_title_sub": title_sub,
                        "name": profile.send_button_name,
                    },
                    summary="send button click",
                )
                if res.success:
                    return res
        keys = list(profile.send_hotkey) if profile else ["enter"]
        self._notify_input_conflict("send_hotkey", {"keys": keys})
        return self._run_tool(
            "send_hotkey",
            {"keys": keys},
            summary="send hotkey enter",
        )

    def _perceive(self, ctx: _SendCtx, *, reason: str) -> None:
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

    def _update_focus_hwnd(self, ctx: _SendCtx, title_sub: str) -> None:
        from iris.automation import window_controller

        wins = window_controller.find_windows_by_title_substring(title_sub)
        if wins and wins[0].hwnd > 0:
            ctx.last_focus_hwnd = wins[0].hwnd

    def _notify_input_conflict(self, tool_name: str, params: dict[str, Any]) -> None:
        if not is_input_conflict_tool(tool_name):
            return
        announce = input_conflict_message(tool_name, params)
        push_activity_line(f"SendMessageFlow: input_conflict — {announce[:80]}")
        notify = getattr(self._agent, "_on_user_notify", None)
        if notify is not None:
            notify(announce)
            delay = float(getattr(self._agent, "_input_notify_delay", 2.0) or 2.0)
            time.sleep(max(0.5, min(delay, 8.0)))

    def _run_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        summary: str,
    ) -> AutomationToolResult:
        return self._agent._run_tool_direct(
            tool_name,
            params,
            summary=summary[:200],
            approved=True,
        )
