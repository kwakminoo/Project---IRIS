"""오케스트레이터 도구 등록 및 순차 실행."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from iris.assistant.action_plan import PlanStep
from iris.assistant.safety_guard import quick_block_user_text
from iris.assistant.tool_layer import is_search_intent
from iris.core.command_router import CommandKind, classify_command

if TYPE_CHECKING:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.ai.gemma_client import GemmaClient, ChatMessage


@dataclass
class ToolRunContext:
    """한 턴 실행 중 공유 상태."""

    user_text: str
    intent: CommandKind | None = None
    observations: list[str] = field(default_factory=list)
    direct_reply: str | None = None
    stop: bool = False


@dataclass(frozen=True)
class ToolResult:
    observation: str
    stop: bool = False
    direct_reply: str | None = None


ToolHandler = Callable[[PlanStep, ToolRunContext], ToolResult]


class ToolRegistry:
    """계획 단계별 도구 실행기."""

    def __init__(
        self,
        assistant: IrisAssistant,
        gemma: GemmaClient,
        *,
        build_finalize_messages: Callable[[str, list[str]], list[ChatMessage]] | None = None,
    ) -> None:
        self._assistant = assistant
        self._gemma = gemma
        self._build_finalize = build_finalize_messages
        self._handlers: dict[str, ToolHandler] = {
            "safety_check": self._safety_check,
            "intent_route": self._intent_route,
            "assistant_dispatch": self._assistant_dispatch,
            "monitoring_status": self._monitoring_status,
            "gemma_finalize": self._gemma_finalize,
        }

    def execute(self, step: PlanStep, ctx: ToolRunContext) -> ToolResult:
        handler = self._handlers.get(step.tool)
        if handler is None:
            obs = f"알 수 없는 도구: {step.tool}"
            ctx.observations.append(obs)
            return ToolResult(observation=obs, stop=True)
        result = handler(step, ctx)
        ctx.observations.append(result.observation)
        if result.direct_reply:
            ctx.direct_reply = result.direct_reply
        if result.stop:
            ctx.stop = True
        return result

    def _safety_check(self, _step: PlanStep, ctx: ToolRunContext) -> ToolResult:
        block = quick_block_user_text(ctx.user_text)
        if block:
            return ToolResult(
                observation=f"안전 차단: {block}",
                stop=True,
                direct_reply=f"Iris: {block}",
            )
        return ToolResult(observation="안전 검사 통과")

    def _intent_route(self, _step: PlanStep, ctx: ToolRunContext) -> ToolResult:
        kind = ctx.intent if ctx.intent is not None else classify_command(ctx.user_text)
        ctx.intent = kind
        if is_search_intent(kind):
            return ToolResult(
                observation=f"검색 의도: {kind.name} — UI 웹 검색 경로로 위임",
                stop=True,
                direct_reply="__DELEGATE_SEARCH__",
            )
        return ToolResult(observation=f"의도 분류: {kind.name}")

    def _assistant_dispatch(self, _step: PlanStep, ctx: ToolRunContext) -> ToolResult:
        kind = ctx.intent or CommandKind.GENERAL_CHAT
        # 승인·모드·단일 액션은 기존 IrisAssistant 멀티턴 흐름 유지
        if kind is not CommandKind.GENERAL_CHAT:
            reply = self._assistant.handle_user_text(ctx.user_text, routed=kind)
            if reply:
                return ToolResult(
                    observation=f"assistant_dispatch 응답 ({kind.name})",
                    stop=True,
                    direct_reply=reply,
                )
            return ToolResult(observation=f"assistant_dispatch 빈 응답 ({kind.name})")

        reply = self._assistant.handle_user_text(ctx.user_text, routed=kind)
        if reply:
            return ToolResult(
                observation="assistant_dispatch 일반 대화 외 응답",
                stop=True,
                direct_reply=reply,
            )
        return ToolResult(observation="assistant_dispatch: 후속 Gemma 요약 필요")

    def _monitoring_status(self, _step: PlanStep, ctx: ToolRunContext) -> ToolResult:
        reply = self._assistant.monitoring_status_reply()
        return ToolResult(
            observation="monitoring_status 조회 완료",
            stop=True,
            direct_reply=reply,
        )

    def _gemma_finalize(self, step: PlanStep, ctx: ToolRunContext) -> ToolResult:
        only_if_empty = bool(step.args.get("only_if_no_direct_reply", True))
        if only_if_empty and ctx.direct_reply:
            return ToolResult(observation="직접 응답이 있어 gemma_finalize 생략")

        if ctx.direct_reply and not only_if_empty:
            return ToolResult(
                observation="기존 direct_reply 유지",
                direct_reply=ctx.direct_reply,
                stop=True,
            )

        messages = self._build_finalize_messages(ctx.user_text, ctx.observations)
        text = self._gemma.chat(messages)
        return ToolResult(
            observation="gemma_finalize 완료",
            stop=True,
            direct_reply=text,
        )

    def _build_finalize_messages(self, user_text: str, observations: list[str]) -> list:
        from iris.ai.gemma_client import ChatMessage
        from iris.ai.prompt_builder import IRIS_SYSTEM_PROMPT

        if self._build_finalize is not None:
            return self._build_finalize(user_text, observations)

        mem_block = ""
        try:
            mem_block = self._assistant.memory.build_extra_context()
        except AttributeError:
            pass

        obs_block = "\n".join(f"- {o}" for o in observations) or "- (없음)"
        system = (
            IRIS_SYSTEM_PROMPT
            + "\n\n[역할]\n"
            "당신은 Iris 실행 오케스트레이터의 최종 요약 단계입니다. "
            "아래 observation만 근거로 한국어로 짧고 명확하게 답하세요. "
            "새로운 컴퓨터 조작을 제안하거나 실행하지 마세요."
        )
        if mem_block:
            system += "\n\n[기억·작업 세션]\n" + mem_block
        user = (
            f"[사용자 요청]\n{user_text}\n\n"
            f"[실행 observation]\n{obs_block}\n\n"
            "위 내용을 바탕으로 사용자에게 최종 답변을 작성하세요."
        )
        return [
            ChatMessage("system", system),
            ChatMessage("user", user),
        ]
