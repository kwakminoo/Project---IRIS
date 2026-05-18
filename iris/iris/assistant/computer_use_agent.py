"""Computer Use — Perceive → Plan → Act → Verify multi-step 루프 (Phase B)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
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
from iris.automation.tool_types import AutomationToolContext, AutomationToolResult
from iris.config.settings import Settings

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

앱 실행:
- params.app_key가 있고 app_paths에 있으면 launch_app
- 없거나 실패 시: Win 검색(포커스+type_text) · UIA(uia_click) · focus_window · type_text · send_hotkey

인식(Perception):
- perceive_desktop (권장), uia_snapshot, read_screen_summary, list_open_windows

행동(Action) 우선순위:
1. send_hotkey  2. uia_click  3. focus_window + type_text  4. click(x,y) — 좌표는 최후
- launch_app, focus_window, open_url, search_web, get_system_info
- run_shell → approval_required (로그인·결제·삭제·셸·시스템 설정도 step_failed 또는 승인 대기)

종료:
- step_complete: 목표 **확실히** 달성, reason에 한국어 요약. 직전 perceive/uia_snapshot 성공 필수.
- step_failed: 더 이상 진행 불가 (로그인·결제·삭제 필요 시 여기 또는 approval)
- ask_user: 목표·slots만으로 불충분할 때. step_complete 금지. params.question 또는 reason에 **사용자 질문 1개만** (한국어)

## 선택 레시피 (예시일 뿐, 유일 경로 아님)
YouTube 재생·검색:
- slots.query 또는 goal에서 검색어 추론. 없으면 ask_user로 query 질문.
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
        ctx = ComputerUseContext(goal=goal, slots=slot_map)
        ctx.observations.append(_format_goal_slots_hint(goal, slot_map))
        self._append_recipe_hints(ctx)

        db = self._assistant._db
        db.insert_log("computer_use", "start", goal[:500])
        self._assistant.memory.save_task_session(goal[:200])

        # 스텝 0: Perception
        self._run_perceive_desktop(ctx, reason="loop_start")

        llm_failures = 0
        exit_tag = "running"  # success | failure | max_steps | approval | parse_abort | verify_abort
        for step_idx in range(self._max_steps):
            if ctx.done:
                break

            raw = self._gemma.chat(self._build_planner_messages(ctx))
            if self._is_llm_unavailable(raw):
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
                if not self._has_recent_perceive(ctx):
                    ctx.verify_skip_count += 1
                    ctx.observations.append(
                        "verify_required: step_complete 전 perceive_desktop 또는 uia_snapshot 필요"
                    )
                    if ctx.verify_skip_count >= _MAX_VERIFY_SKIP:
                        ctx.done = True
                        ctx.final_message = (
                            "화면 검증 없이 완료할 수 없어 중단했습니다. 다시 요청해 주세요."
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
            obs = self._execute_tool(parsed, step_idx)
            ctx.observations.append(obs)

            if obs.startswith("approval_required:"):
                ctx.done = True
                ctx.final_message = obs[len("approval_required:") :].strip()
                exit_tag = "approval"
                break

            # Verify (B): 매 Act 후 재인식
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
                self._delegate_to_external(ctx, exit_tag, backend)

        tools_run = [s.tool for s in ctx.steps_taken if s.tool not in ("step_complete", "step_failed")]
        self._assistant.memory.save_task_session(
            goal[:200],
            tools_run=tools_run,
            observations=[o[:200] for o in ctx.observations[-20:]],
        )
        db.insert_log("computer_use", "end", ctx.final_message[:500])

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
            [ChatMessage("system", system), ChatMessage("user", raw_clean)]
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

    def _execute_tool(self, step: ComputerUseStep, step_idx: int) -> str:
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
            return f"approval_required: {preview} ('응' / '승인' 후 다시 요청해 주세요.)"

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
