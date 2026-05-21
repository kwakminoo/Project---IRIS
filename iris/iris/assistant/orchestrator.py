"""Agent loop — JSON 계획 → 도구 순차 실행 → observation 요약."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.ai.gemma_client import ChatMessage
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.action_plan import ActionPlan, PlanStep, default_plan, parse_action_plan, plan_to_json
from iris.assistant.tool_registry import ToolRegistry, ToolRunContext
from iris.core.command_router import CommandKind

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient
    from iris.storage.database import Database

PLANNER_SYSTEM = """당신은 Iris 실행 계획기입니다.
사용자 요청에 대해 즉시 답변하지 말고, 아래 메타 도구만 사용하는 JSON 실행 계획만 출력하세요.
PC 조작·multi-step 작업은 ComputerUseAgent가 담당합니다. 이 계획기는 메타 파이프라인만 사용합니다.

허용 도구:
- safety_check: 입력 안전 검사
- intent_route: 의도 분류
- assistant_dispatch: 모드·승인·앱 실행 등 기존 IrisAssistant 처리
- monitoring_status: 모니터링 대상 요약 (모니터링 질문일 때만)
- gemma_finalize: observation을 바탕으로 최종 한국어 답변 (마지막에 반드시 포함)

출력 형식 (JSON만, 다른 텍스트 없음):
{
  "goal": "한 줄 목표",
  "steps": [
    {"tool": "safety_check", "args": {}},
    {"tool": "intent_route", "args": {}},
    {"tool": "assistant_dispatch", "args": {}},
    {"tool": "gemma_finalize", "args": {"only_if_no_direct_reply": true}}
  ]
}
"""


class AgentOrchestrator:
    """Gemma 직접 채팅 대신 계획·도구·요약 루프를 수행."""

    DELEGATE_SEARCH = "__DELEGATE_SEARCH__"

    def __init__(
        self,
        db: Database,
        assistant: IrisAssistant,
        gemma: GemmaClient,
        *,
        max_steps: int = 12,
    ) -> None:
        self._db = db
        self._assistant = assistant
        self._gemma = gemma
        self._max_steps = max_steps
        self._tools = ToolRegistry(assistant, gemma)

    def run(self, user_text: str, *, intent: CommandKind | None = None) -> str:
        """한 턴 Agent loop. 검색 위임 시 DELEGATE_SEARCH 반환."""
        ctx = ToolRunContext(user_text=user_text, intent=intent)
        plan = self._build_plan(user_text)
        self._db.insert_log("orchestrator", "plan", plan_to_json(plan)[:2000])

        executed = 0
        for step in plan.steps:
            if ctx.stop or executed >= self._max_steps:
                break
            result = self._tools.execute(step, ctx)
            executed += 1
            if result.direct_reply == self.DELEGATE_SEARCH:
                return self.DELEGATE_SEARCH
            if result.direct_reply and ctx.stop:
                return self._ensure_iris_prefix(result.direct_reply)

        if ctx.direct_reply:
            return self._ensure_iris_prefix(ctx.direct_reply)

        # 계획에 finalize가 생략된 경우 안전망
        fin = self._tools.execute(
            PlanStep("gemma_finalize", {"only_if_no_direct_reply": False}),
            ctx,
        )
        if fin.direct_reply and fin.direct_reply != self.DELEGATE_SEARCH:
            return self._ensure_iris_prefix(fin.direct_reply)
        return "Iris: 요청을 처리했지만 응답을 생성하지 못했습니다."

    def _build_plan(self, user_text: str) -> ActionPlan:
        messages: list[ChatMessage] = [
            ChatMessage("system", PLANNER_SYSTEM),
            ChatMessage("user", user_text),
        ]
        raw = self._gemma.chat(messages, purpose=LlmPurpose.ORCHESTRATOR_PLAN)
        parsed = parse_action_plan(raw)
        if parsed is not None:
            return parsed
        self._db.insert_log("orchestrator", "plan_fallback", raw[:500] if raw else "empty")
        return default_plan(user_text)

    @staticmethod
    def _ensure_iris_prefix(text: str) -> str:
        t = text.strip()
        if t.startswith("Iris:"):
            return t
        return f"Iris: {t}"
