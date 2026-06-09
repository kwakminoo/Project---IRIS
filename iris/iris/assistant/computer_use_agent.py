"""Computer Use — Perceive → Plan → Act → Verify multi-step 루프 (Phase B)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.action_plan import (
    ALLOWED_COMPUTER_USE_TOOLS,
    ComputerUseFullPlan,
    ComputerUsePlanItem,
    ComputerUseStep,
    full_plan_from_dict,
    full_plan_to_dict,
    parse_computer_use_full_plan,
    parse_computer_use_step,
)
from iris.assistant.cu_prompts import (
    COMPUTER_USE_PLANNER_SYSTEM,
    CU_CHECKPOINT_VERIFY_SYSTEM,
    CU_FULL_PLAN_PLANNER_SYSTEM,
    CU_REPAIR_PLANNER_SYSTEM,
    cu_meta_system_prompt,
)
from iris.assistant.execution_tier_policy import (
    EXECUTION_TIER_PLANNER_BLOCK,
    input_conflict_message,
    is_input_conflict_tool,
    should_skip_quick_launch,
    tool_tier_rank,
)
from iris.assistant.external_agent_adapter import (
    ExternalAgentBackend,
    build_external_backend,
    log_external_delegate,
    run_external_delegate,
    tier4_delegate_active,
)
from iris.core.activity_privacy import summarize_tool_params
from iris.core.activity_sink import push_activity_line
from iris.automation.tool_types import AutomationToolContext, AutomationToolResult
from iris.config.app_index import display_name_for_key, resolve_app_for_goal
from iris.config.settings import Settings
from iris.core.context_manager import PendingComputerUseGoal
from iris.assistant.cu_vision import capture_planner_screenshot
from iris.assistant.tool_user_reply import (
    format_pending_tool_user_message,
    format_user_approval_message,
)
from iris.automation import window_controller

# 하위 호환 re-export (테스트·외부 import)
__all__ = [
    "ComputerUseAgent",
    "USER_QUESTION_PREFIX",
    "COMPUTER_USE_PLANNER_SYSTEM",
    "CU_FULL_PLAN_PLANNER_SYSTEM",
    "CU_CHECKPOINT_VERIFY_SYSTEM",
    "CU_REPAIR_PLANNER_SYSTEM",
    "format_user_approval_message",
    "format_pending_tool_user_message",
    "extract_user_question",
]

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient
    from iris.assistant.cu_perception import PerceptionObservation
    from iris.automation.tool_registry import AutomationToolRegistry

_MAX_VERIFY_SKIP = 3
_MAX_PLAY_COMPLETE_SKIP = 3

@dataclass
class ComputerUseContext:
    """한 번의 Computer Use 루프 세션 상태."""

    goal: str
    slots: dict[str, Any] = field(default_factory=dict)
    steps_taken: list[ComputerUseStep] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    done: bool = False
    final_message: str = ""
    verify_skip_count: int = 0
    last_focus_hwnd: int = 0  # focus_window 성공 시 기록 — 플래너 스크린샷 대상
    input_conflict_announced: set[str] = field(default_factory=set)
    full_plan: ComputerUseFullPlan | None = None
    executed_through_index: int = -1
    last_checkpoint_result: Any = None  # CheckpointVerifyResult | None
    repair_attempt: int = 0
    last_perception: PerceptionObservation | None = None
    perception_history: list[PerceptionObservation] = field(default_factory=list)
    last_type_verify: bool | None = None  # type_text 직후 text_input_controller 검증 결과


USER_QUESTION_PREFIX = "USER_QUESTION:"


class ComputerUseAgent:
    """Gemma + AutomationToolRegistry 기반 multi-step PC 제어 루프."""

    def __init__(
        self,
        assistant: IrisAssistant,
        gemma: GemmaClient,
        registry: AutomationToolRegistry,
        *,
        max_steps: int = 20,
        tier4_backend: ExternalAgentBackend | None = None,
    ) -> None:
        self._assistant = assistant
        self._gemma = gemma
        self._registry = registry
        self._max_steps = max_steps
        # 테스트용 Tier4 백엔드 주입(None이면 settings에서 조립)
        self._tier4_backend_override = tier4_backend

    def run(
        self,
        goal: str,
        slots: dict[str, Any] | None = None,
        *,
        on_user_notify: Callable[[str], None] | None = None,
    ) -> str:
        """목표(+slots)로 PAV 루프 실행 후 사용자용 최종 문자열 (Iris: 접두사 없음)."""
        goal = goal.strip()
        if not goal:
            return "요청이 비어 있습니다."

        slot_map = dict(slots) if slots else {}
        self._on_user_notify = on_user_notify
        notify_delay = float(
            getattr(self._assistant._settings, "computer_use_input_notify_delay_seconds", 2.0)
            or 2.0
        )
        self._input_notify_delay = max(0.5, min(notify_delay, 8.0))
        db = self._assistant._db

        # 스킬 Flow — PAV·quick launch·recipe_hint 우회
        from iris.assistant.action_skills import resolve_skill_id, run_skill, should_dispatch_skill

        if should_dispatch_skill(slot_map):
            skill_id = resolve_skill_id(slot_map) or ""
            push_activity_line(f"ComputerUse: skill={skill_id} fixed flow.")
            return run_skill(skill_id, self, goal, slot_map)

        # 사전 라우팅: 단순 앱 실행은 launch_app 1스텝 (복합·멀티스텝·스킬은 PAV)
        quick_msg = None
        if not should_skip_quick_launch(goal, slot_map):
            quick_msg = self._try_simple_app_launch(goal, slot_map)
        if quick_msg is not None:
            push_activity_line("ComputerUse: quick launch_app path (tier-1 bypass).")
            db.insert_log("computer_use", "quick_launch_app", goal[:500])
            self._assistant.memory.save_task_session(
                goal[:200], tools_run=["launch_app"], observations=[quick_msg[:200]]
            )
            return quick_msg

        ctx = ComputerUseContext(goal=goal, slots=slot_map)
        ctx.observations.append(_format_goal_slots_hint(goal, slot_map))
        self._append_recipe_hints(ctx)

        push_activity_line("ComputerUse: session started (planner + PAV).")
        db.insert_log("computer_use", "start", goal[:500])
        self._assistant.memory.save_task_session(goal[:200])

        # 스텝 0: Perception
        push_activity_line("ComputerUse: perceive phase (loop_start).")
        self._run_perceive_desktop(ctx, reason="loop_start")

        exit_tag = "running"  # success | failure | max_steps | approval | parse_abort | verify_abort
        if self._full_plan_enabled():
            exit_tag = self._run_full_plan_session(ctx)
            if exit_tag == "llm_unavailable":
                push_activity_line("ComputerUse: planner LLM unavailable — aborting.")
                db.insert_log("computer_use", "llm_fallback", ctx.final_message[:200])
                return ctx.final_message or FALLBACK_KO
        else:
            exit_tag = self._run_step_planner_session(ctx)

        if not ctx.done and exit_tag in ("running", "max_steps"):
            exit_tag = "max_steps"
            ctx.final_message = (
                f"단계 제한({self._max_steps}스텝)에 도달해 중단했습니다. "
                "이어서 진행하려면 다시 요청해 주세요."
            )

        return self._finish_cu_session(ctx, exit_tag=exit_tag)

    def resume_after_critical_approval(
        self,
        pending: PendingComputerUseGoal,
        *,
        on_user_notify: Callable[[str], None] | None = None,
    ) -> str:
        """CRITICAL 승인 후 CU 루프 재개 — 승인 스텝 실행 → checkpoint verify → 루프 계속."""
        self._on_user_notify = on_user_notify
        notify_delay = float(
            getattr(self._assistant._settings, "computer_use_input_notify_delay_seconds", 2.0)
            or 2.0
        )
        self._input_notify_delay = max(0.5, min(notify_delay, 8.0))
        db = self._assistant._db

        ctx = ComputerUseContext(
            goal=pending.goal.strip(),
            slots=dict(pending.slots),
            observations=list(pending.cu_observations),
            executed_through_index=pending.executed_through_index,
        )
        if pending.full_plan_snapshot:
            ctx.full_plan = full_plan_from_dict(pending.full_plan_snapshot)

        tool_name = pending.pending_tool_name.strip()
        params = dict(pending.pending_tool_params)
        if not tool_name:
            return "승인된 도구 정보가 없습니다."

        push_activity_line(
            f"ComputerUse: resume after CRITICAL approval tool={tool_name!r}."
        )
        db.insert_log(
            "computer_use",
            "resume_critical",
            f"tool={tool_name} mode={pending.cu_mode or 'step_planner'}"[:500],
        )
        self._assistant.memory.save_task_session(
            pending.goal[:200],
            tools_run=[tool_name],
            approvals=[f"approved:{tool_name}"],
        )

        step = ComputerUseStep(
            tool_name,
            params,
            pending.pending_tool_preview or tool_name,
        )
        ctx.steps_taken.append(step)
        summary = step.reason or tool_name
        result = self._run_tool_direct(
            tool_name,
            params,
            summary=summary,
            approved=True,
        )
        obs = self._format_tool_observation(tool_name, result)
        ctx.observations.append(obs)

        if not result.success:
            ctx.done = True
            ctx.final_message = result.message or obs
            return self._finish_cu_session(ctx, exit_tag="failure")

        plan_index = pending.pending_plan_index
        if plan_index >= 0:
            ctx.executed_through_index = max(ctx.executed_through_index, plan_index)

        mode = (pending.cu_mode or "step_planner").strip()
        cp_id = (pending.pending_checkpoint_id or "").strip()
        exit_tag = "running"

        if mode == "repair" and ctx.full_plan is not None:
            checkpoint_id = cp_id or "cp_final"
            if not self._run_checkpoint_verify(
                ctx,
                checkpoint_id,
                executed_through_index=pending.executed_through_index,
            ):
                exit_tag = self._run_repair_for_checkpoint(
                    ctx,
                    checkpoint_id=checkpoint_id,
                    executed_through_index=pending.executed_through_index,
                )
            else:
                exit_tag = self._iterate_full_plan_items(
                    ctx,
                    start_after_index=pending.executed_through_index,
                )
        elif mode == "full_plan" and ctx.full_plan is not None:
            item = self._find_plan_item_by_index(ctx, plan_index)
            checkpoint_id = (item.checkpoint_id if item else None) or cp_id or None
            if checkpoint_id:
                if self._run_checkpoint_verify(
                    ctx,
                    checkpoint_id,
                    executed_through_index=plan_index,
                ):
                    exit_tag = self._iterate_full_plan_items(
                        ctx,
                        start_after_index=plan_index,
                    )
                else:
                    exit_tag = self._run_repair_for_checkpoint(
                        ctx,
                        checkpoint_id=checkpoint_id,
                        executed_through_index=plan_index,
                    )
                    if exit_tag == "checkpoint_ok":
                        exit_tag = self._iterate_full_plan_items(
                            ctx,
                            start_after_index=plan_index,
                        )
            else:
                push_activity_line(
                    f"ComputerUse: verify — perceive after tool={tool_name!r}."
                )
                self._run_perceive_desktop(ctx, reason=f"after_{tool_name}")
                exit_tag = self._iterate_full_plan_items(
                    ctx,
                    start_after_index=plan_index,
                )
        else:
            push_activity_line(
                f"ComputerUse: verify — perceive after tool={tool_name!r}."
            )
            self._run_perceive_desktop(ctx, reason=f"after_{tool_name}")
            exit_tag = self._run_step_planner_session(ctx)

        if not ctx.done and exit_tag in ("running", "max_steps"):
            exit_tag = "max_steps"
            ctx.final_message = (
                f"단계 제한({self._max_steps}스텝)에 도달해 중단했습니다. "
                "이어서 진행하려면 다시 요청해 주세요."
            )

        return self._finish_cu_session(ctx, exit_tag=exit_tag)

    def _finish_cu_session(self, ctx: ComputerUseContext, *, exit_tag: str) -> str:
        """CU 세션 종료 — Tier4·task_session 저장 후 사용자 메시지."""
        db = self._assistant._db
        settings = self._assistant._settings
        if exit_tag not in (
            "success",
            "approval",
            "ask_user",
            "repair_exhausted",
        ) and tier4_delegate_active(
            settings if isinstance(settings, Settings) else None
        ):
            backend = self._resolve_tier4_backend()
            if backend is not None and backend.is_available():
                try:
                    bid = backend.backend_id()  # type: ignore[misc]
                except Exception:
                    bid = type(backend).__name__
                push_activity_line(f"ComputerUse: Tier4 delegate backend={bid!r}.")
                self._delegate_to_external(ctx, exit_tag, backend)

        tools_run = [
            s.tool for s in ctx.steps_taken if s.tool not in ("step_complete", "step_failed")
        ]
        self._assistant.memory.save_task_session(
            ctx.goal[:200],
            tools_run=tools_run,
            observations=[o[:200] for o in ctx.observations[-20:]],
        )
        db.insert_log("computer_use", "end", (ctx.final_message or "")[:500])
        push_activity_line(
            f"ComputerUse: session finished exit={exit_tag} step_count={len(ctx.steps_taken)}."
        )
        return ctx.final_message

    def _resolve_tier4_backend(self) -> ExternalAgentBackend | None:
        """테스트 주입 우선, 이후 Settings 기반."""
        if self._tier4_backend_override is not None:
            return self._tier4_backend_override
        st = self._assistant._settings
        if not isinstance(st, Settings):
            return None
        return build_external_backend(st)

    def _build_delegate_context(self, ctx: ComputerUseContext, exit_tag: str) -> str:
        """위임용 단락 압축: 목표·관측·실패 이유."""
        obs_blob = " ".join(o.replace("\n", " ")[:140] for o in ctx.observations[-14:])
        return (
            f"목표: {ctx.goal[:400]}. "
            f"로컬 루프 종료 사유: {exit_tag}. "
            f"사용자 안내 초안: {ctx.final_message[:220]}. "
            f"누적 관측: {obs_blob}"
        )[:4500]

    def _summarize_delegate_raw(self, raw: str) -> str:
        """외부 CLI 로그를 한국어로 재요약(원문 노출 최소화)."""
        raw_clean = raw.strip()[:1800]
        system = (
            "당신은 Iris 비서입니다. 아래는 내부 보조 실행 로그입니다. "
            "사용자에게 한국어 2~4문장으로만 안내하세요. CLI·제품 브랜드명은 쓰지 마세요. "
            "로그 원문을 그대로 붙이지 마세요. 존댓말로 마무리하세요."
        )
        reply = self._gemma.chat(
            [ChatMessage("system", system), ChatMessage("user", raw_clean)],
            purpose=LlmPurpose.COMPUTER_USE,
            lane="computer_use",
        )
        if self._is_llm_unavailable(reply) or not reply.strip():
            return (
                "Iris가 대신 처리를 시도했습니다. "
                "화면에서 결과를 한 번 확인해 주시면 감사하겠습니다."
            )
        return reply.strip()[:800]

    def _delegate_to_external(
        self,
        ctx: ComputerUseContext,
        exit_tag: str,
        backend: ExternalAgentBackend,
    ) -> None:
        """Tier 4 위임 + SQLite 로그 + 선택적 perceive 검증."""
        db = self._assistant._db
        context = self._build_delegate_context(ctx, exit_tag)
        res, duration_ms = run_external_delegate(
            backend, goal=ctx.goal[:800], context=context
        )
        summary = self._summarize_delegate_raw(res.message)
        extra = ""
        st = self._assistant._settings
        if (
            res.success
            and isinstance(st, Settings)
            and st.external_agent_verify_perception
        ):
            verify = self._run_tool_direct(
                "perceive_desktop",
                {},
                summary="tier4_verify",
                approved=True,
            )
            if not verify.success:
                extra = " 보조 처리는 완료되었다고 했으나, 화면 확인이 필요합니다."
        elif not res.success:
            summary = f"{summary} 필요하면 화면을 확인해 주세요."

        log_external_delegate(
            db,
            goal=ctx.goal,
            backend=res.backend_id,
            success=res.success,
            duration_ms=duration_ms,
            summary_ko=(summary + extra).strip(),
        )
        ctx.final_message = (summary + extra).strip()

    @staticmethod
    def _append_recipe_hints(ctx: ComputerUseContext) -> None:
        """일반 CU용 선택 URL 힌트 — media_play/skill_id는 MediaSkill이 처리."""
        if str(ctx.slots.get("skill_id") or "").strip() == "media_play":
            return
        if str(ctx.slots.get("task_type") or "").strip().lower() == "media_play":
            return
        g_low = ctx.goal.lower()
        app_hint = str(ctx.slots.get("app_hint") or "").lower()
        if "유튜브" not in ctx.goal and "youtube" not in g_low and app_hint != "youtube":
            return
        query = ctx.slots.get("query") or ctx.slots.get("search_query") or ctx.slots.get("title")
        if isinstance(query, str) and query.strip():
            from iris.automation.media_urls import build_youtube_search_url

            try:
                url = build_youtube_search_url(query.strip())
                ctx.observations.append(
                    f"recipe_hint: youtube open_url → {url[:240]}"
                )
            except ValueError:
                pass

    def _cu_vlm_enabled(self) -> bool:
        st = self._assistant._settings
        return bool(getattr(st, "computer_use_vlm_enabled", False))

    def _cu_vlm_on_planner(self) -> bool:
        """플래너(full/step) VLM — 마스터 스위치 + planner 플래그."""
        if not self._cu_vlm_enabled():
            return False
        st = self._assistant._settings
        return bool(getattr(st, "computer_use_vlm_on_planner", False))

    def _cu_vlm_on_verify(self) -> bool:
        """checkpoint verify·repair VLM — 마스터 스위치 + verify 플래그."""
        if not self._cu_vlm_enabled():
            return False
        st = self._assistant._settings
        return bool(getattr(st, "computer_use_vlm_on_verify", True))

    def _cu_vision_model(self) -> str | None:
        st = self._assistant._settings
        name = str(getattr(st, "computer_use_vision_model", "") or "").strip()
        return name or None

    def _full_plan_enabled(self) -> bool:
        st = self._assistant._settings
        return bool(getattr(st, "computer_use_full_plan_enabled", True))

    def _capture_planner_screenshot(self, ctx: ComputerUseContext) -> tuple[bytes | None, str]:
        """VLM on 시 플래너용 스크린샷."""
        if not self._cu_vlm_on_planner():
            return None, "vlm_planner_off"
        png, meta = capture_planner_screenshot(ctx)
        if png:
            push_activity_line(f"ComputerUse: planner vision attached ({meta}).")
        else:
            push_activity_line(f"ComputerUse: planner vision skipped ({meta}).")
        return png, meta

    def _capture_verify_screenshot(self, ctx: ComputerUseContext) -> tuple[bytes | None, str]:
        """VLM on 시 verify·repair용 스크린샷."""
        if not self._cu_vlm_on_verify():
            return None, "vlm_verify_off"
        png, meta = capture_planner_screenshot(ctx)
        if png:
            push_activity_line(f"ComputerUse: verify vision attached ({meta}).")
        else:
            push_activity_line(f"ComputerUse: verify vision skipped ({meta}).")
        return png, meta

    def _run_step_planner_session(self, ctx: ComputerUseContext) -> str:
        """레거시 1스텝 플래너 PAV 루프."""
        llm_failures = 0
        exit_tag = "running"
        for step_idx in range(self._max_steps):
            if ctx.done:
                break

            raw = self._planner_step(ctx)
            if self._is_llm_unavailable(raw):
                ctx.final_message = raw
                return "llm_unavailable"

            parsed = parse_computer_use_step(raw)
            if parsed is None:
                llm_failures += 1
                ctx.observations.append(
                    f"parse_error: JSON 파싱 실패 (시도 {llm_failures})"
                )
                if llm_failures >= 3:
                    ctx.done = True
                    ctx.final_message = (
                        "실행 계획을 이해하지 못했습니다. 요청을 다시 말씀해 주세요."
                    )
                    exit_tag = "parse_abort"
                    break
                continue

            llm_failures = 0
            push_activity_line(
                f"ComputerUse: planner step {step_idx + 1} chose tool={parsed.tool!r}."
            )
            exit_tag = self._execute_parsed_step(ctx, parsed, step_idx)
            if exit_tag != "running":
                break

        if not ctx.done and exit_tag == "running":
            exit_tag = "max_steps"
        return exit_tag

    def _run_full_plan_session(self, ctx: ComputerUseContext) -> str:
        """초기 Perceive 후 전체 plans[] 1회 작성 → 순차 실행 → checkpoint Verify."""
        push_activity_line("ComputerUse: full plan planner (1-shot).")
        raw = self._full_plan_planner(ctx)
        if self._is_llm_unavailable(raw):
            ctx.final_message = raw
            return "llm_unavailable"

        full_plan = parse_computer_use_full_plan(raw)
        if full_plan is None:
            push_activity_line("ComputerUse: full plan parse failed — fallback step planner.")
            ctx.observations.append("full_plan_parse_error: JSON 파싱 실패 — 1스텝 플래너 폴백")
            return self._run_step_planner_session(ctx)

        push_activity_line(
            f"ComputerUse: full plan id={full_plan.plan_id!r} steps={len(full_plan.plans)}."
        )
        ctx.full_plan = full_plan
        self._assistant._db.insert_log(
            "computer_use",
            "full_plan",
            f"id={full_plan.plan_id} steps={len(full_plan.plans)}"[:500],
        )

        if len(full_plan.plans) == 1 and full_plan.plans[0].tool == "ask_user":
            return self._handle_ask_user_step(ctx, full_plan.plans[0])

        return self._iterate_full_plan_items(ctx, start_after_index=-1)

    def _iterate_full_plan_items(
        self,
        ctx: ComputerUseContext,
        *,
        start_after_index: int = -1,
    ) -> str:
        """full_plan.plans 순차 실행 — start_after_index 이후 스텝만."""
        full_plan = ctx.full_plan
        if full_plan is None:
            return "repair_exhausted"

        for item in full_plan.plans:
            if ctx.done:
                break
            if item.index <= start_after_index:
                continue

            step = ComputerUseStep(item.tool, dict(item.params), item.reason)
            ctx.steps_taken.append(step)
            push_activity_line(
                f"ComputerUse: full plan step {item.index} tool={item.tool!r}."
            )

            if item.tool == "ask_user":
                return self._handle_ask_user_step(ctx, item)

            psum = summarize_tool_params(item.tool, dict(item.params))
            push_activity_line(f"ComputerUse: act tool={item.tool} ({psum}).")
            obs = self._execute_tool(
                step,
                item.index,
                cu_ctx=ctx,
                approval_cu_mode="full_plan",
                checkpoint_id=item.checkpoint_id,
            )
            ctx.observations.append(obs)

            if obs.startswith("approval_required:"):
                push_activity_line("ComputerUse: pending CRITICAL tool — approval required.")
                ctx.done = True
                ctx.final_message = obs[len("approval_required:") :].strip()
                return "approval"

            if obs.startswith("tool_fail:"):
                repair_tag = self._repair_after_tool_fail(
                    ctx,
                    item=item,
                    obs=obs,
                )
                if repair_tag == "checkpoint_ok":
                    ctx.executed_through_index = item.index
                    continue
                if repair_tag == "repair_exhausted":
                    ctx.done = False
                    push_activity_line(
                        "ComputerUse: repair exhausted after tool_fail — step planner fallback."
                    )
                    return self._run_step_planner_session(ctx)
                return repair_tag

            ctx.executed_through_index = item.index

            if item.checkpoint_id:
                if self._run_checkpoint_verify(
                    ctx,
                    item.checkpoint_id,
                    executed_through_index=item.index,
                ):
                    continue
                repair_tag = self._run_repair_for_checkpoint(
                    ctx,
                    checkpoint_id=item.checkpoint_id,
                    executed_through_index=item.index,
                )
                if repair_tag == "checkpoint_ok":
                    continue
                if repair_tag == "repair_exhausted":
                    ctx.done = False
                    push_activity_line(
                        "ComputerUse: repair exhausted — step planner fallback."
                    )
                    return self._run_step_planner_session(ctx)
                return repair_tag

            elif item.tool not in (
                "perceive_desktop",
                "list_open_windows",
                "uia_snapshot",
            ):
                push_activity_line(f"ComputerUse: verify — perceive after tool={item.tool!r}.")
                self._run_perceive_desktop(ctx, reason=f"after_{item.tool}")

        if not ctx.done:
            ctx.done = True
            ctx.final_message = self._full_plan_completion_message(full_plan)
            return "success"
        return "running"

    @staticmethod
    def _find_plan_item_by_index(
        ctx: ComputerUseContext,
        plan_index: int,
    ) -> ComputerUsePlanItem | None:
        if ctx.full_plan is None or plan_index < 0:
            return None
        for item in ctx.full_plan.plans:
            if item.index == plan_index:
                return item
        return None

    def _enrich_pending_cu_resume(
        self,
        pending: PendingComputerUseGoal,
        cu_ctx: ComputerUseContext,
        step_idx: int,
        *,
        approval_cu_mode: str,
        checkpoint_id: str | None = None,
    ) -> None:
        """CRITICAL 승인 대기 시 CU 세션 스냅샷을 pending에 저장."""
        pending.pending_plan_index = step_idx
        pending.executed_through_index = cu_ctx.executed_through_index
        pending.cu_mode = approval_cu_mode
        pending.pending_checkpoint_id = (checkpoint_id or "").strip()
        pending.cu_observations = list(cu_ctx.observations[-30:])
        if cu_ctx.full_plan is not None:
            pending.plan_id = cu_ctx.full_plan.plan_id
            pending.full_plan_snapshot = full_plan_to_dict(cu_ctx.full_plan)

    def _save_cu_pending_task_session(
        self,
        pending: PendingComputerUseGoal,
        cu_ctx: ComputerUseContext,
    ) -> None:
        """승인 대기 상태를 task_session에 요약 저장."""
        tools_run = [
            s.tool
            for s in cu_ctx.steps_taken
            if s.tool not in ("step_complete", "step_failed")
        ]
        self._assistant.memory.save_task_session(
            pending.goal[:200],
            tools_run=tools_run,
            observations=[o[:200] for o in cu_ctx.observations[-10:]],
            approvals=[f"pending:{pending.pending_tool_name}"],
        )

    @staticmethod
    def _full_plan_completion_message(full_plan: ComputerUseFullPlan) -> str:
        for item in reversed(full_plan.plans):
            if item.tool not in (
                "perceive_desktop",
                "list_open_windows",
                "uia_snapshot",
                "ask_user",
            ):
                if item.reason.strip():
                    return item.reason.strip()
        return "작업을 완료했습니다."

    def _handle_ask_user_step(
        self, ctx: ComputerUseContext, item: ComputerUsePlanItem
    ) -> str:
        question = str(item.params.get("question") or item.reason or "").strip()
        if not question:
            question = "요청을 조금 더 구체적으로 말씀해 주시겠어요?"
        ctx.done = True
        ctx.final_message = f"{USER_QUESTION_PREFIX} {question}"
        return "ask_user"

    def _execute_parsed_step(
        self,
        ctx: ComputerUseContext,
        parsed: ComputerUseStep,
        step_idx: int,
    ) -> str:
        """파싱된 1스텝 실행 — step_complete/ask_user/approval 등 종료 태그 반환."""
        ctx.steps_taken.append(parsed)

        if parsed.tool == "ask_user":
            return self._handle_ask_user_step(
                ctx,
                ComputerUsePlanItem(
                    index=step_idx,
                    tool="ask_user",
                    params=dict(parsed.params),
                    reason=parsed.reason,
                ),
            )

        if parsed.tool == "step_complete":
            if not self._allow_step_complete(ctx, parsed):
                if ctx.verify_skip_count >= _MAX_VERIFY_SKIP:
                    ctx.done = True
                    ctx.final_message = (
                        ctx.final_message
                        or (
                            "화면·재생 검증 없이 완료할 수 없어 중단했습니다. "
                            "다시 요청해 주세요."
                        )
                    )
                    return "verify_abort"
                return "running"
            ctx.done = True
            ctx.final_message = parsed.reason or "작업을 완료했습니다."
            return "success"

        if parsed.tool == "step_failed":
            ctx.done = True
            ctx.final_message = parsed.reason or "작업을 완료하지 못했습니다."
            return "failure"

        psum = summarize_tool_params(parsed.tool, dict(parsed.params))
        push_activity_line(f"ComputerUse: act tool={parsed.tool} ({psum}).")
        obs = self._execute_tool(
            parsed,
            step_idx,
            cu_ctx=ctx,
            approval_cu_mode="step_planner",
        )
        ctx.observations.append(obs)

        if obs.startswith("approval_required:"):
            push_activity_line("ComputerUse: pending CRITICAL tool — approval required.")
            ctx.done = True
            ctx.final_message = obs[len("approval_required:") :].strip()
            return "approval"

        push_activity_line(f"ComputerUse: verify — perceive after tool={parsed.tool!r}.")
        self._run_perceive_desktop(ctx, reason=f"after_{parsed.tool}")
        return "running"

    def _run_checkpoint_verify(
        self,
        ctx: ComputerUseContext,
        checkpoint_id: str,
        *,
        executed_through_index: int,
    ) -> bool:
        """checkpoint_id 스텝 직후 Verify — perceive + LLM 체크포인트 판정."""
        from iris.assistant.cu_checkpoint_verify import (
            format_checkpoint_fail,
            format_checkpoint_ok,
            mechanical_prerequisites_met,
            verify_checkpoint_hybrid,
        )

        push_activity_line(f"ComputerUse: checkpoint verify {checkpoint_id!r}.")
        self._run_perceive_desktop(ctx, reason=f"checkpoint_{checkpoint_id}")

        ok_gate, block_msg = mechanical_prerequisites_met(
            ctx.observations,
            last_perception=ctx.last_perception,
        )
        if not ok_gate:
            ctx.observations.append(block_msg)
            ctx.observations.append(
                f"checkpoint_fail: {checkpoint_id} | {block_msg.split(':', 1)[-1].strip()}"
            )
            return False

        plans = ctx.full_plan.plans if ctx.full_plan else ()
        plan_id = ctx.full_plan.plan_id if ctx.full_plan else ""
        screenshot_png: bytes | None = None
        if self._cu_vlm_on_verify():
            screenshot_png, _meta = self._capture_verify_screenshot(ctx)

        result, _vision_used = verify_checkpoint_hybrid(
            self._gemma,
            goal=ctx.goal,
            plan_id=plan_id,
            checkpoint_id=checkpoint_id,
            executed_through_index=executed_through_index,
            plans=plans,
            observations=ctx.observations,
            slots=ctx.slots,
            cu_ctx=ctx,
            last_perception=ctx.last_perception,
            screenshot_png=screenshot_png,
        )
        ctx.last_checkpoint_result = result

        if result is None:
            ctx.observations.append(
                f"checkpoint_fail: {checkpoint_id} | LLM verify unavailable"
            )
            return False

        if result.achieved:
            ctx.observations.append(format_checkpoint_ok(result))
            self._assistant._db.insert_log(
                "computer_use",
                "checkpoint_ok",
                f"{checkpoint_id} conf={result.confidence:.2f}"[:500],
            )
            return True

        ctx.observations.append(format_checkpoint_fail(result))
        self._assistant._db.insert_log(
            "computer_use",
            "checkpoint_fail",
            (
                f"{checkpoint_id} kind={result.failure_kind} "
                f"resume={result.resume_from_index} gap={result.gap[:120]}"
            )[:500],
        )
        return False

    def _repair_after_tool_fail(
        self,
        ctx: ComputerUseContext,
        *,
        item: ComputerUsePlanItem,
        obs: str,
    ) -> str:
        """tool_fail 시 synthetic verify → Repair (즉시 step planner 폴백 금지)."""
        from iris.assistant.cu_checkpoint_verify import CheckpointVerifyResult

        cp_id = item.checkpoint_id or "cp_final"
        synthetic = CheckpointVerifyResult(
            checkpoint_id=cp_id,
            achieved=False,
            failure_kind="unknown",
            progress_summary="",
            gap=obs,
            last_ok_index=max(-1, item.index - 1),
            resume_from_index=item.index,
            confidence=0.0,
        )
        ctx.last_checkpoint_result = synthetic
        ctx.observations.append(f"tool_fail_repair: step {item.index}")
        push_activity_line(
            f"ComputerUse: tool_fail at step {item.index} — repair before fallback."
        )
        return self._run_repair_for_checkpoint(
            ctx,
            checkpoint_id=cp_id,
            executed_through_index=item.index,
        )

    def _run_repair_for_checkpoint(
        self,
        ctx: ComputerUseContext,
        *,
        checkpoint_id: str,
        executed_through_index: int,
    ) -> str:
        """체크포인트 실패 후 Repair Planner 루프 — checkpoint_ok | ask_user | repair_exhausted."""
        from iris.assistant.cu_checkpoint_verify import CheckpointVerifyResult
        from iris.assistant.cu_repair_planner import llm_repair_plan
        from iris.assistant.cu_repair_templates import build_mechanical_repair_steps

        if ctx.full_plan is None:
            return "repair_exhausted"

        template_tried = False
        while True:
            verify = ctx.last_checkpoint_result
            if not isinstance(verify, CheckpointVerifyResult) or verify.achieved:
                return "checkpoint_ok"

            if not template_tried:
                template_tried = True
                mech_steps = build_mechanical_repair_steps(
                    verify, ctx.slots, ctx.observations
                )
                if mech_steps:
                    push_activity_line(
                        f"ComputerUse: mechanical repair template "
                        f"({verify.failure_kind}, {len(mech_steps)} steps)."
                    )
                    self._assistant._db.insert_log(
                        "computer_use",
                        "repair_template",
                        (
                            f"{checkpoint_id} kind={verify.failure_kind} "
                            f"steps={len(mech_steps)}"
                        )[:500],
                    )
                    abort = self._execute_repair_steps(
                        ctx,
                        mech_steps,
                        parent_checkpoint_id=checkpoint_id,
                    )
                    if abort == "approval":
                        return "approval"
                    if self._run_checkpoint_verify(
                        ctx,
                        checkpoint_id,
                        executed_through_index=executed_through_index,
                    ):
                        push_activity_line(
                            f"ComputerUse: checkpoint {checkpoint_id!r} "
                            "recovered after mechanical repair."
                        )
                        return "checkpoint_ok"
                    push_activity_line(
                        "ComputerUse: mechanical repair template failed — LLM repair."
                    )

            ctx.repair_attempt += 1
            push_activity_line(
                f"ComputerUse: repair attempt {ctx.repair_attempt}/3 for {checkpoint_id!r}."
            )
            if ctx.repair_attempt > 3:
                ctx.done = True
                ctx.final_message = (
                    verify.gap
                    or verify.progress_summary
                    or "체크포인트 검증에 실패했습니다."
                )
                self._assistant._db.insert_log(
                    "computer_use",
                    "repair_exhausted",
                    f"{checkpoint_id} attempts=3"[:500],
                )
                return "repair_exhausted"

            screenshot_png: bytes | None = None
            if self._cu_vlm_on_verify():
                screenshot_png, _meta = self._capture_verify_screenshot(ctx)

            repair = llm_repair_plan(
                self._gemma,
                goal=ctx.goal,
                plan_id=ctx.full_plan.plan_id,
                original_plans=ctx.full_plan.plans,
                verify_result=verify,
                observations=ctx.observations,
                slots=ctx.slots,
                repair_attempt=ctx.repair_attempt,
                screenshot_png=screenshot_png,
            )

            if repair is None:
                ctx.observations.append(
                    f"repair_parse_error: attempt={ctx.repair_attempt} checkpoint={checkpoint_id}"
                )
                if ctx.repair_attempt >= 3:
                    ctx.done = True
                    ctx.final_message = verify.gap or verify.progress_summary or "Repair 계획 파싱 실패"
                    return "repair_exhausted"
                continue

            self._assistant._db.insert_log(
                "computer_use",
                "repair_plan",
                (
                    f"id={repair.plan_id} attempt={repair.repair_attempt} "
                    f"steps={len(repair.repair_steps)} fail={repair.recommend_fail}"
                )[:500],
            )

            if repair.ask_user:
                return self._handle_ask_user_step(
                    ctx,
                    ComputerUsePlanItem(
                        index=-1,
                        tool="ask_user",
                        params={"question": repair.ask_user},
                        reason=repair.gap or verify.gap,
                    ),
                )

            if repair.recommend_fail or (
                not repair.repair_steps and ctx.repair_attempt >= 3
            ):
                ctx.done = True
                ctx.final_message = repair.gap or verify.gap or verify.progress_summary
                return "repair_exhausted"

            if not repair.repair_steps:
                ctx.observations.append(
                    f"repair_empty: attempt={ctx.repair_attempt} checkpoint={checkpoint_id}"
                )
                continue

            abort = self._execute_repair_steps(
                ctx,
                repair.repair_steps,
                parent_checkpoint_id=checkpoint_id,
            )
            if abort == "approval":
                return "approval"
            if abort == "tool_fail":
                push_activity_line("ComputerUse: repair step tool_fail — re-verify.")

            if self._run_checkpoint_verify(
                ctx,
                checkpoint_id,
                executed_through_index=executed_through_index,
            ):
                push_activity_line(
                    f"ComputerUse: checkpoint {checkpoint_id!r} recovered after repair."
                )
                return "checkpoint_ok"

    def _execute_repair_steps(
        self,
        ctx: ComputerUseContext,
        repair_steps: tuple[Any, ...],
        *,
        parent_checkpoint_id: str = "",
    ) -> str:
        """repair_steps[] 순차 실행 — approval | tool_fail | ok."""
        for ridx, item in enumerate(repair_steps):
            step = ComputerUseStep(item.tool, dict(item.params), item.reason)
            ctx.steps_taken.append(step)
            push_activity_line(
                f"ComputerUse: repair step {ridx} tool={item.tool!r}."
            )

            psum = summarize_tool_params(item.tool, dict(item.params))
            push_activity_line(f"ComputerUse: act tool={item.tool} ({psum}).")
            cp_for_pending = item.checkpoint_id or parent_checkpoint_id or None
            obs = self._execute_tool(
                step,
                item.index,
                cu_ctx=ctx,
                approval_cu_mode="repair",
                checkpoint_id=cp_for_pending,
            )
            ctx.observations.append(obs)

            if obs.startswith("approval_required:"):
                ctx.done = True
                ctx.final_message = obs[len("approval_required:") :].strip()
                return "approval"

            if obs.startswith("tool_fail:"):
                return "tool_fail"

            if item.checkpoint_id:
                if self._run_checkpoint_verify(
                    ctx,
                    item.checkpoint_id,
                    executed_through_index=item.index,
                ):
                    continue
        return "ok"

    def _full_plan_planner(self, ctx: ComputerUseContext) -> str:
        """전체 플랜 1회 — VLM on 시 창 PNG + chat_with_images."""
        png, _meta = self._capture_planner_screenshot(ctx)
        messages = self._build_full_plan_messages(ctx, png)
        return self._invoke_planner_llm(messages, png=png)

    def _build_full_plan_messages(
        self,
        ctx: ComputerUseContext,
        screenshot_png: bytes | None = None,
    ) -> list[ChatMessage]:
        from iris.assistant.action_plan import FULL_PLAN_ALLOWED_TOOLS

        obs_text = "\n".join(f"[obs] {o}" for o in ctx.observations[-24:])
        slots_line = ""
        if ctx.slots:
            slots_line = f"slots: {json.dumps(ctx.slots, ensure_ascii=False)[:400]}\n"
        shot_tag = "screenshot_attached=yes" if screenshot_png else "screenshot_attached=no"
        vision_line = "첨부 화면이 현재 PC 상태입니다.\n" if screenshot_png else ""
        user_body = (
            f"목표: {ctx.goal}\n"
            f"{slots_line}"
            f"{shot_tag}\n"
            f"초기 Perceive observation:\n{obs_text}\n\n"
            f"{vision_line}"
            "전체 plans[] JSON만 출력하세요."
        )
        allowed = ", ".join(sorted(FULL_PLAN_ALLOWED_TOOLS))
        system = cu_meta_system_prompt(
            CU_FULL_PLAN_PLANNER_SYSTEM,
            extra=f"{EXECUTION_TIER_PLANNER_BLOCK}\n\n허용 도구 목록: {allowed}",
        )
        images: tuple[bytes, ...] = (screenshot_png,) if screenshot_png else ()
        return [
            ChatMessage("system", system),
            ChatMessage("user", user_body, images=images),
        ]

    def _planner_step(self, ctx: ComputerUseContext) -> str:
        """플래너 1스텝 — VLM on 시 창 PNG + chat_with_images."""
        png, _meta = self._capture_planner_screenshot(ctx)
        messages = self._build_planner_messages(ctx, png)
        return self._invoke_planner_llm(messages, png=png)

    def _invoke_planner_llm(
        self,
        messages: list[ChatMessage],
        *,
        png: bytes | None,
    ) -> str:
        """플래너 LLM 호출 — 구형 mock(chat(messages)만) 호환."""
        model_override = self._cu_vision_model()
        llm_kw: dict[str, Any] = {
            "purpose": LlmPurpose.COMPUTER_USE,
            "lane": "computer_use",
        }
        if model_override:
            llm_kw["model_override"] = model_override
        if png and hasattr(self._gemma, "chat_with_images"):
            try:
                raw, _used = self._gemma.chat_with_images(messages, **llm_kw)
                return raw
            except TypeError:
                pass
        try:
            return self._gemma.chat(messages, **llm_kw)
        except TypeError:
            return self._gemma.chat(messages)

    def _build_planner_messages(
        self,
        ctx: ComputerUseContext,
        screenshot_png: bytes | None = None,
    ) -> list[ChatMessage]:
        obs_text = "\n".join(f"[obs] {o}" for o in ctx.observations[-24:])
        slots_line = ""
        if ctx.slots:
            slots_line = f"slots: {json.dumps(ctx.slots, ensure_ascii=False)[:400]}\n"
        shot_tag = "screenshot_attached=yes" if screenshot_png else "screenshot_attached=no"
        vision_line = (
            "첨부 화면이 현재 PC 상태입니다.\n" if screenshot_png else ""
        )
        user_body = (
            f"목표: {ctx.goal}\n"
            f"{slots_line}"
            f"{shot_tag}\n"
            f"지금까지 observation:\n{obs_text}\n\n"
            f"{vision_line}"
            "다음 한 스텝 JSON만 출력하세요."
        )
        allowed = ", ".join(sorted(ALLOWED_COMPUTER_USE_TOOLS))
        system = (
            f"{COMPUTER_USE_PLANNER_SYSTEM}\n\n{EXECUTION_TIER_PLANNER_BLOCK}\n\n"
            f"허용 도구 목록: {allowed}"
        )
        images: tuple[bytes, ...] = (screenshot_png,) if screenshot_png else ()
        return [
            ChatMessage("system", system),
            ChatMessage("user", user_body, images=images),
        ]

    def _run_perceive_desktop(self, ctx: ComputerUseContext, *, reason: str) -> None:
        """build_perception → ctx.last_perception 갱신 + LLM용 observation 한 줄."""
        from iris.assistant.cu_perception import (
            build_perception,
            perception_to_observation_line,
            windows_to_observation_line,
        )

        push_activity_line(
            f"ComputerUse: perceive list_open_windows + perceive_desktop reason={reason!r}."
        )
        perception = build_perception(
            self._registry,
            self._assistant._settings,
            focus_hwnd=ctx.last_focus_hwnd,
            app_paths=self._assistant._app_paths,
            database=self._assistant._db,
        )
        ctx.last_perception = perception
        ctx.perception_history.append(perception)

        ctx.observations.append(windows_to_observation_line(perception))
        pd_raw = perception.raw_tool_results.get("perceive_desktop") or {}
        if pd_raw.get("success"):
            ctx.observations.append(perception_to_observation_line(perception))
            # Phase 6: monitoring/ 이벤트·타깃 → monitor_hint observation 1줄
            from iris.monitoring.cu_hint_injector import append_monitor_hint_observations

            pd_meta: dict[str, Any] = {}
            pd_detail = str(pd_raw.get("detail") or "")
            if pd_detail.strip():
                try:
                    parsed = json.loads(pd_detail)
                    if isinstance(parsed, dict):
                        pd_meta = parsed
                except json.JSONDecodeError:
                    pd_meta = {}
            append_monitor_hint_observations(
                ctx.observations,
                self._assistant._db,
                active_window_title=perception.active_window_title,
                active_process_name=perception.active_process_name,
                perceive_monitor_hint=str(pd_meta.get("monitor_hint") or ""),
            )
        else:
            fail_msg = str(pd_raw.get("message") or "perceive_desktop 실패")
            ctx.observations.append(f"perceive: fail | {fail_msg[:200]}")

        self._assistant._db.insert_log(
            "computer_use",
            "perceive",
            f"reason={reason} source={perception.perception_source}"[:500],
        )

    @staticmethod
    def _has_recent_perceive(ctx: ComputerUseContext) -> bool:
        from iris.assistant.cu_perception import has_valid_perception

        return has_valid_perception(ctx.last_perception)

    def _allow_step_complete(
        self,
        ctx: ComputerUseContext,
        parsed: ComputerUseStep,
    ) -> bool:
        """
        step_complete 허용 여부 — perceive 필수, media_action=play 시 기계 게이트 추가.
        거부 시 observation에 verify_required 메시지 추가.
        """
        from iris.assistant.media_verify import (
            observation_blob_from,
            play_step_complete_allowed,
            verify_media_with_llm_retries,
        )

        if not self._has_recent_perceive(ctx):
            ctx.verify_skip_count += 1
            ctx.observations.append(
                "verify_required: step_complete 전 perceive_desktop 또는 uia_snapshot 필요"
            )
            return False

        allowed, reject_msg = play_step_complete_allowed(ctx.slots, ctx.observations)
        if allowed:
            return True

        # Media Flow 미경유 play — LLM verify 보조(최대 _MAX_PLAY_COMPLETE_SKIP회)
        action = str(ctx.slots.get("media_action") or "").strip().lower()
        if action == "play":
            ctx.verify_skip_count += 1
            blob = observation_blob_from(ctx.observations)
            screenshot_png: bytes | None = None
            if self._cu_vlm_enabled():
                screenshot_png, _meta = capture_planner_screenshot(ctx)
            verify, _vision_used = verify_media_with_llm_retries(
                self._gemma,
                goal=ctx.goal,
                media_action="play",
                observation_blob=blob,
                screenshot_png=screenshot_png,
                max_attempts=1,
            )
            if verify and verify.achieved:
                from iris.assistant.media_verify import format_media_verify_ok

                ctx.observations.append(
                    format_media_verify_ok("play", verify.evidence)
                )
                return True
            if verify and verify.missing:
                reject_msg = (
                    f"verify_required: play not confirmed — {verify.missing}"
                )
            ctx.observations.append(reject_msg)
            if ctx.verify_skip_count >= _MAX_PLAY_COMPLETE_SKIP:
                detail = (verify.missing or verify.evidence) if verify else ""
                ctx.final_message = (
                    "재생 화면을 확인하지 못해 완료할 수 없습니다. "
                    "브라우저에서 재생 상태를 확인하시거나 다시 요청해 주세요."
                    + (f" ({detail})" if detail else "")
                )
            return False

        ctx.verify_skip_count += 1
        ctx.observations.append(reject_msg)
        return False

    def _try_simple_app_launch(self, goal: str, slots: dict[str, Any]) -> str | None:
        """Router slots 기반 단순 앱 열기 — launch_app 1스텝 (플래너·run_shell 우회)."""
        task = str(slots.get("task_type") or "").strip().lower()
        if task != "open_app":
            return None
        app_key = str(slots.get("app_key") or "").strip()
        if not app_key:
            app_key, _exe = resolve_app_for_goal(
                goal,
                self._assistant._app_paths,
                db=self._assistant._db,
            )
            if not app_key:
                return (
                    f"{USER_QUESTION_PREFIX} "
                    "어떤 앱을 실행할지 파악하지 못했습니다. "
                    "예: Cursor, Chrome, Edge, 메모장."
                )
        disp = str(slots.get("display_name") or "").strip() or display_name_for_key(
            app_key, self._assistant._db
        )
        result = self._run_tool_direct(
            "launch_app",
            {"app_key": app_key, "display_name": disp},
            summary=f"앱 실행: {disp}",
            approved=True,
        )
        if result.success:
            return format_pending_tool_user_message("launch_app", result, disp)
        return None

    def run_pending_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        summary: str = "",
        approved: bool = True,
    ) -> AutomationToolResult:
        """승인된 CRITICAL 도구 1스텝만 실행 (CU 루프 재시작 없음)."""
        return self._run_tool_direct(
            tool_name,
            dict(params),
            summary=summary or tool_name,
            approved=approved,
        )

    def _execute_tool(
        self,
        step: ComputerUseStep,
        step_idx: int,
        *,
        cu_ctx: ComputerUseContext,
        approval_cu_mode: str = "step_planner",
        checkpoint_id: str | None = None,
    ) -> str:
        """도구 실행 후 observation 문자열 반환."""
        summary = step.reason or f"{step.tool} step {step_idx + 1}"
        tool_ctx = AutomationToolContext(
            params=dict(step.params),
            approved=False,
            auto_approve_low_risk=self._assistant._db.get_auto_approve_low_risk(),
            app_paths=self._assistant._app_paths,
            settings=self._assistant._settings,
            database=self._assistant._db,
            summary=summary[:200],
        )

        tier = tool_tier_rank(step.tool)
        push_activity_line(
            f"ComputerUse: execution_tier={tier} tool={step.tool!r}."
        )

        if is_input_conflict_tool(step.tool) and step.tool not in cu_ctx.input_conflict_announced:
            announce = input_conflict_message(step.tool, step.params)
            push_activity_line(f"ComputerUse: input_conflict_notice — {announce[:80]}")
            notify = getattr(self, "_on_user_notify", None)
            if notify is not None:
                notify(announce)
                time.sleep(getattr(self, "_input_notify_delay", 2.0))
            cu_ctx.input_conflict_announced.add(step.tool)

        if self._registry.needs_approval(step.tool, tool_ctx):
            preview = self._registry.preview(step.tool, tool_ctx)
            user_msg = format_user_approval_message(step.tool, preview, step.params)
            pending = PendingComputerUseGoal(
                goal=cu_ctx.goal,
                risk_hint="critical",
                prompt=user_msg,
                slots=dict(cu_ctx.slots),
                pending_tool_name=step.tool,
                pending_tool_params=dict(step.params),
                pending_tool_preview=preview,
            )
            self._enrich_pending_cu_resume(
                pending,
                cu_ctx,
                step_idx,
                approval_cu_mode=approval_cu_mode,
                checkpoint_id=checkpoint_id,
            )
            self._assistant.ctx.pending_cu = pending
            self._save_cu_pending_task_session(pending, cu_ctx)
            return f"approval_required: {user_msg}"

        result = self._run_tool_direct(
            step.tool,
            step.params,
            summary=summary,
            approved=True,
        )
        if step.tool == "focus_window" and result.success:
            sub = str(step.params.get("title_sub") or "").strip()
            if sub:
                wins = window_controller.find_windows_by_title_substring(sub)
                if wins and wins[0].hwnd > 0:
                    cu_ctx.last_focus_hwnd = wins[0].hwnd
        if step.tool == "type_text":
            detail = str(result.detail or "")
            if result.success:
                cu_ctx.last_type_verify = "|ok" in detail
            else:
                cu_ctx.last_type_verify = False
        return self._format_tool_observation(step.tool, result)

    def _run_tool_direct(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        summary: str,
        approved: bool,
    ) -> AutomationToolResult:
        """ActionExecutor와 동일한 컨텍스트로 Registry 실행."""
        ctx = AutomationToolContext(
            params=params,
            approved=approved,
            auto_approve_low_risk=self._assistant._db.get_auto_approve_low_risk(),
            app_paths=self._assistant._app_paths,
            settings=self._assistant._settings,
            database=self._assistant._db,
            summary=summary[:200],
        )
        return self._registry.run(tool_name, ctx)

    @staticmethod
    def _format_tool_observation(tool_name: str, result: AutomationToolResult) -> str:
        status = "ok" if result.success else "fail"
        body = result.message[:200]
        if result.detail:
            body = f"{body} | {result.detail[:300]}"
        prefix = "tool_ok" if result.success else "tool_fail"
        return f"{prefix}: {tool_name} {status} | {body}"

    @staticmethod
    def _is_llm_unavailable(text: str) -> bool:
        t = text.strip()
        return t == FALLBACK_KO or "로컬 언어 모델에 연결할 수 없습니다" in t


def _format_goal_slots_hint(goal: str, slots: dict[str, Any]) -> str:
    """observation 첫 줄 — goal·slots 힌트."""
    parts = [f"goal: {goal[:300]}"]
    if slots:
        parts.append(f"slots: {json.dumps(slots, ensure_ascii=False)[:240]}")
    return " | ".join(parts)


def extract_user_question(message: str) -> str | None:
    """CU ask_user 종료 시 사용자에게 보여줄 질문."""
    body = message.strip()
    if body.startswith("Iris:"):
        body = body[5:].strip()
    if not body.startswith(USER_QUESTION_PREFIX):
        return None
    q = body[len(USER_QUESTION_PREFIX) :].strip()
    return q or None
