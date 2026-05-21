"""Computer Use — Perceive → Plan → Act → Verify multi-step 루프 (Phase B)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.action_plan import (
    ALLOWED_COMPUTER_USE_TOOLS,
    ComputerUseStep,
    parse_computer_use_step,
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

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient
    from iris.automation.tool_registry import AutomationToolRegistry

COMPUTER_USE_PLANNER_SYSTEM = """당신은 Iris Computer Use 플래너입니다.
사용자 PC 목표(goal)와 slots를 읽고 **한 번에 한 스텝**만 JSON으로 출력하세요.
Unity·Discord·Excel·유튜브·카톡·임의 앱·웹 모두 동일한 범용 절차를 따릅니다.

## 범용 자비스 절차 (모든 앱·웹)
1. loop_start: list_open_windows + perceive_desktop (이미 observation에 있을 수 있음)
2. Act: 조작 도구 **1스텝**만 실행
3. Verify: perceive_desktop 또는 uia_snapshot으로 화면 검증
4. 목표 달성 + 직전 perceive 근거 → step_complete

앱 실행 (Windows 기본·등록 앱):
- notepad(메모장), calc(계산기), mspaint(그림판) 등은 **run_shell 금지** → launch_app + app_key
- app_paths·app_index에 있는 app_key는 launch_app 우선
- run_shell은 멀티 명령·파이프(|)·스크립트(.ps1/.bat)·설치/삭제·레지스트리 등 **셸이 필수일 때만**
- 단순 notepad/calc 실행에 run_shell 사용하지 마세요

인식(Perception):
- perceive_desktop (권장), uia_snapshot, read_screen_summary, list_open_windows

행동(Action) 우선순위:
1. send_hotkey  2. uia_click  3. focus_window + type_text  4. click(x,y) — 좌표는 최후
- launch_app, focus_window, open_url, search_web, get_system_info
- run_shell → approval_required (CRITICAL, 사용자 확인 후 1스텝만 실행)

## 파라미터 (엄수)
| 도구 | 필수/주요 키 | 의미 |
|------|----------------|------|
| focus_window | title_sub | **OS 창 제목** 부분 문자열 (예: "YouTube", "Chrome") — 영상 제목 아님 |
| uia_snapshot, uia_click | window_title_sub | 대상 **창** 식별 |
| uia_click | name (또는 automation_id) | 창 **내부 UI 요소** 텍스트; 검색 결과 영상 제목은 여기 또는 ranker pick_name |
| perceive_desktop | focus_hint (선택) | 인식 전 포커스할 창 힌트 |
| open_url | url | 전체 URL |
| (미디어 slots) | search_query | **검색/API용** 곡명·영상명·키워드 — Router가 채움, 플래너 임의 변경 금지 |

- 창 = title_sub / window_title_sub (브라우저·앱 창 제목 일부)
- 콘텐츠 검색어 = slots.search_query (Router 제공)
- 검색 결과 클릭 = uia_click.name (ranker가 고른 제목)
- **금지:** 영상 제목을 title_sub/title_hint에 넣지 말 것 → search_query 또는 uia_click.name
- send_hotkey: params.keys (배열). 단일 key는 비권장

종료:
- step_complete: 목표 **확실히** 달성, reason에 한국어 요약. 직전 perceive/uia_snapshot 성공 필수.
- step_failed: 더 이상 진행 불가 (로그인·결제·삭제 필요 시 여기 또는 approval)
- ask_user: 목표·slots만으로 불충분할 때. step_complete 금지. params.question 또는 reason에 **사용자 질문 1개만** (한국어)

## 선택 레시피 (예시일 뿐, 유일 경로 아님)
YouTube 재생·검색:
- slots.search_query 사용 (Router 제공). 없으면 ask_user로 검색어 질문.
- open_url에 `https://www.youtube.com/results?search_query=` + URL인코딩(query) 사용
  (코드: iris.automation.media_urls.build_youtube_search_url)
- 순서: open_url → perceive → uia_click/send_hotkey(재생) → perceive → step_complete
- youtube.com 홈만 여는 것은 목표 달성이 아님.

출력 (JSON만):
{"tool": "도구이름", "params": {}, "reason": "이 스텝 이유"}
"""

_PERCEIVE_OBS_RE = re.compile(
    r"^(perceive:|tool_ok:\s*(perceive_desktop|uia_snapshot)\s)",
    re.IGNORECASE,
)
_MAX_VERIFY_SKIP = 3
_MAX_PLAY_COMPLETE_SKIP = 3

# 단순 앱 열기 — CU 플래너·run_shell 우회
_SIMPLE_OPEN_APP_RE = re.compile(
    r"(켜|열어|열기|실행|띄워|띄우|launch|open|start)",
    re.IGNORECASE,
)
_COMPLEX_GOAL_RE = re.compile(
    r"(그리고|보내|입력|검색|틀어|재생|메시지|삭제|설치|로그인|결제|파일)",
    re.IGNORECASE,
)


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

    def run(self, goal: str, slots: dict[str, Any] | None = None) -> str:
        """목표(+slots)로 PAV 루프 실행 후 사용자용 최종 문자열 (Iris: 접두사 없음)."""
        goal = goal.strip()
        if not goal:
            return "요청이 비어 있습니다."

        slot_map = dict(slots) if slots else {}
        db = self._assistant._db

        # 미디어 검색·재생 — 고정 Media Flow (플래너 send_hotkey 단독 complete 방지)
        from iris.assistant.media_playback_flow import MediaPlaybackFlow, should_run_media_flow

        if should_run_media_flow(slot_map):
            push_activity_line("ComputerUse: MediaPlaybackFlow (router media slots).")
            return MediaPlaybackFlow(self).run(goal, slot_map)

        # 사전 라우팅: 단순 앱 실행은 launch_app 1스텝 (B/C 인덱스·별칭)
        quick_msg = self._try_simple_app_launch(goal)
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

        llm_failures = 0
        exit_tag = "running"  # success | failure | max_steps | approval | parse_abort | verify_abort
        for step_idx in range(self._max_steps):
            if ctx.done:
                break

            raw = self._gemma.chat(
                self._build_planner_messages(ctx),
                purpose=LlmPurpose.COMPUTER_USE,
                lane="computer_use",
            )
            if self._is_llm_unavailable(raw):
                push_activity_line("ComputerUse: planner LLM unavailable — aborting.")
                db.insert_log("computer_use", "llm_fallback", raw[:200])
                return raw

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
            ctx.steps_taken.append(parsed)

            if parsed.tool == "ask_user":
                question = str(
                    parsed.params.get("question") or parsed.reason or ""
                ).strip()
                if not question:
                    question = "요청을 조금 더 구체적으로 말씀해 주시겠어요?"
                ctx.done = True
                ctx.final_message = f"{USER_QUESTION_PREFIX} {question}"
                exit_tag = "ask_user"
                break

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
                        exit_tag = "verify_abort"
                        break
                    continue
                ctx.done = True
                ctx.final_message = parsed.reason or "작업을 완료했습니다."
                exit_tag = "success"
                break

            if parsed.tool == "step_failed":
                ctx.done = True
                ctx.final_message = parsed.reason or "작업을 완료하지 못했습니다."
                exit_tag = "failure"
                break

            # Act
            psum = summarize_tool_params(parsed.tool, dict(parsed.params))
            push_activity_line(f"ComputerUse: act tool={parsed.tool} ({psum}).")
            obs = self._execute_tool(parsed, step_idx, cu_ctx=ctx)
            ctx.observations.append(obs)

            if obs.startswith("approval_required:"):
                push_activity_line("ComputerUse: pending CRITICAL tool — approval required.")
                ctx.done = True
                ctx.final_message = obs[len("approval_required:") :].strip()
                exit_tag = "approval"
                break

            # Verify (B): 매 Act 후 재인식
            push_activity_line(f"ComputerUse: verify — perceive after tool={parsed.tool!r}.")
            self._run_perceive_desktop(ctx, reason=f"after_{parsed.tool}")

        if not ctx.done:
            exit_tag = "max_steps"
            ctx.final_message = (
                f"단계 제한({self._max_steps}스텝)에 도달해 중단했습니다. "
                "이어서 진행하려면 다시 요청해 주세요."
            )

        # Tier 4: 로컬 실패·한계만 위임(성공·승인 대기·LLM 불가 제외)
        settings = self._assistant._settings
        if exit_tag not in ("success", "approval", "ask_user") and tier4_delegate_active(
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

        tools_run = [s.tool for s in ctx.steps_taken if s.tool not in ("step_complete", "step_failed")]
        self._assistant.memory.save_task_session(
            goal[:200],
            tools_run=tools_run,
            observations=[o[:200] for o in ctx.observations[-20:]],
        )
        db.insert_log("computer_use", "end", ctx.final_message[:500])
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
        """YouTube 등 선택 레시피 URL 힌트 (플래너 강제 아님)."""
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

    def _build_planner_messages(self, ctx: ComputerUseContext) -> list[ChatMessage]:
        obs_text = "\n".join(f"[obs] {o}" for o in ctx.observations[-24:])
        slots_line = ""
        if ctx.slots:
            slots_line = f"slots: {json.dumps(ctx.slots, ensure_ascii=False)[:400]}\n"
        user_body = (
            f"목표: {ctx.goal}\n"
            f"{slots_line}\n"
            f"지금까지 observation:\n{obs_text}\n\n"
            "다음 한 스텝 JSON만 출력하세요."
        )
        allowed = ", ".join(sorted(ALLOWED_COMPUTER_USE_TOOLS))
        system = f"{COMPUTER_USE_PLANNER_SYSTEM}\n\n허용 도구 목록: {allowed}"
        return [
            ChatMessage("system", system),
            ChatMessage("user", user_body),
        ]

    def _run_perceive_desktop(self, ctx: ComputerUseContext, *, reason: str) -> None:
        """perceive_desktop + list_open_windows로 observation 추가."""
        push_activity_line(
            f"ComputerUse: perceive list_open_windows + perceive_desktop reason={reason!r}."
        )
        win_obs = self._run_tool_direct(
            "list_open_windows",
            {},
            summary="창 목록",
            approved=True,
        )
        if win_obs.success:
            detail = (win_obs.detail or win_obs.message or "")[:400]
            ctx.observations.append(f"windows: {detail or win_obs.message[:200]}")
        else:
            ctx.observations.append(f"windows: {win_obs.message[:200]}")

        pd = self._run_tool_direct(
            "perceive_desktop",
            {},
            summary=f"perceive {reason}",
            approved=True,
        )
        source = "unknown"
        if pd.success:
            ctx.observations.append(pd.message[:500])
            if pd.detail:
                try:
                    meta = json.loads(pd.detail)
                    source = str(meta.get("perception_source") or "unknown")
                except Exception:
                    pass
        else:
            ctx.observations.append(f"perceive: fail | {pd.message[:200]}")

        self._assistant._db.insert_log(
            "computer_use",
            "perceive",
            f"reason={reason} source={source}"[:500],
        )

    @staticmethod
    def _has_recent_perceive(ctx: ComputerUseContext) -> bool:
        for obs in reversed(ctx.observations[-8:]):
            if _PERCEIVE_OBS_RE.search(obs.strip()):
                return True
        return False

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
            verify = verify_media_with_llm_retries(
                self._gemma,
                goal=ctx.goal,
                media_action="play",
                observation_blob=blob,
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

    def _try_simple_app_launch(self, goal: str) -> str | None:
        """단순 앱 열기 — launch_app 1스텝 (플래너·run_shell 우회)."""
        if not _SIMPLE_OPEN_APP_RE.search(goal):
            return None
        if _COMPLEX_GOAL_RE.search(goal):
            return None
        app_key, _exe = resolve_app_for_goal(
            goal,
            self._assistant._app_paths,
            db=self._assistant._db,
        )
        if not app_key:
            return None
        disp = display_name_for_key(app_key, self._assistant._db)
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

        if self._registry.needs_approval(step.tool, tool_ctx):
            preview = self._registry.preview(step.tool, tool_ctx)
            user_msg = format_user_approval_message(step.tool, preview, step.params)
            # 승인 후 1스텝 실행용 pending 저장
            self._assistant.ctx.pending_cu = PendingComputerUseGoal(
                goal=cu_ctx.goal,
                risk_hint="critical",
                prompt=user_msg,
                slots=dict(cu_ctx.slots),
                pending_tool_name=step.tool,
                pending_tool_params=dict(step.params),
                pending_tool_preview=preview,
            )
            return f"approval_required: {user_msg}"

        result = self._run_tool_direct(
            step.tool,
            step.params,
            summary=summary,
            approved=True,
        )
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


def format_user_approval_message(
    tool: str,
    preview: str,
    params: dict[str, Any] | None = None,
) -> str:
    """내부 preview 노출 없이 승인 요청 문장."""
    action = _approval_action_line(tool, preview, params or {})
    return f"이 작업을 진행하려면 확인이 필요합니다. 진행할까요?\n{action}"


def _approval_action_line(
    tool: str,
    preview: str,
    params: dict[str, Any],
) -> str:
    """사용자용 구체 action 한 줄 (쉘·preview 원문 미노출)."""
    if tool == "launch_app":
        disp = str(params.get("display_name") or params.get("app_key") or "앱")
        return f"- {disp} 실행"
    if tool == "run_shell":
        cmd = str(params.get("command") or "").strip().lower()
        if re.search(r"notepad|메모장", cmd) or re.search(r"notepad|메모장", preview, re.I):
            return "- 메모장 실행"
        if re.search(r"\bcalc\b|계산기", cmd) or re.search(r"calc|계산기", preview, re.I):
            return "- 계산기 실행"
        if re.search(r"mspaint|그림판|paint", cmd, re.I):
            return "- 그림판 실행"
        return "- 셸 명령 실행"
    if tool == "type_text":
        return "- 키보드 입력"
    return "- 요청하신 PC 작업"


def format_pending_tool_user_message(
    tool_name: str,
    result: AutomationToolResult,
    display_hint: str = "",
) -> str:
    """승인 후 1스텝 실행 결과 → 사용자 메시지."""
    if not result.success:
        reason = (result.message or "실행에 실패했습니다.").strip()
        return f"요청하신 작업을 실행하지 못했습니다. {reason}"

    if tool_name == "launch_app":
        disp = display_hint or str(result.message or "앱")
        if "실행" in disp:
            return f"요청하신 작업을 실행했습니다. ({disp})"
        return f"요청하신 작업을 실행했습니다. ({disp} 실행)"

    if tool_name == "run_shell":
        if re.search(r"notepad|메모장", result.message or "", re.I):
            return "요청하신 작업을 실행했습니다. (메모장)"
        return "요청하신 작업을 실행했습니다."

    return "요청하신 작업을 실행했습니다."


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
