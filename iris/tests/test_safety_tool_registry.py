"""Safety Guard·ToolRegistry — 레거시 Orchestrator 대체 스모크."""

from __future__ import annotations

from pathlib import Path

from iris.assistant.action_plan import PlanStep
from iris.assistant.orchestrator import AgentOrchestrator
from iris.assistant.tool_registry import ToolRegistry, ToolRunContext
from iris.core.command_router import CommandKind
from tests.support.fakes import FakeGemma, make_test_assistant


def test_safety_block_stops_orchestrator_loop(tmp_path: Path) -> None:
    gemma = FakeGemma(
        planner_json='{"goal":"x","steps":[{"tool":"safety_check","args":{}},{"tool":"gemma_finalize","args":{}}]}'
    )
    assistant = make_test_assistant(tmp_path, gemma)
    orch = AgentOrchestrator(assistant._db, assistant, gemma)  # type: ignore[arg-type]
    reply = orch.run("비밀번호 입력해줘")
    assert "차단" in reply


def test_tool_registry_search_delegate(tmp_path: Path) -> None:
    gemma = FakeGemma(planner_json='{"goal":"검색","steps":[{"tool":"intent_route","args":{}}]}')
    assistant = make_test_assistant(tmp_path, gemma)
    registry = ToolRegistry(assistant, gemma)  # type: ignore[arg-type]
    ctx = ToolRunContext(user_text="요즘 영화 뭐 있어", intent=CommandKind.MOVIE_SEARCH)
    result = registry.execute(PlanStep("intent_route"), ctx)
    assert result.direct_reply == AgentOrchestrator.DELEGATE_SEARCH
