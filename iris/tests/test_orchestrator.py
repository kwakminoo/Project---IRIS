"""AgentOrchestrator·ToolRegistry 스모크 테스트."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

from iris.ai.gemma_client import ChatMessage
from iris.assistant.action_plan import PlanStep
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.orchestrator import AgentOrchestrator
from iris.assistant.tool_registry import ToolRegistry, ToolRunContext
from iris.automation.action_executor import ActionExecutor
from iris.core.command_router import CommandKind
from iris.storage.database import Database


class _FakeGemma:
    def __init__(self, planner_json: str, finalize: str = "요약 답변입니다.") -> None:
        self._planner_json = planner_json
        self._finalize = finalize
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        if messages and "실행 계획기" in messages[0].content:
            return self._planner_json
        return self._finalize


def _make_assistant(tmp_path: Path, gemma: _FakeGemma) -> IrisAssistant:
    db = Database(path=tmp_path / "test.db")
    executor = ActionExecutor(db, {})
    assistant = IrisAssistant(db, executor, gemma, {})  # type: ignore[arg-type]
    return assistant


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path


def test_orchestrator_general_chat_finalize(tmp_db_path: Path) -> None:
    planner = """
    {
      "goal": "인사",
      "steps": [
        {"tool": "safety_check", "args": {}},
        {"tool": "intent_route", "args": {}},
        {"tool": "assistant_dispatch", "args": {}},
        {"tool": "gemma_finalize", "args": {"only_if_no_direct_reply": true}}
      ]
    }
    """
    gemma = _FakeGemma(planner, finalize="안녕하세요, 무엇을 도와드릴까요?")
    assistant = _make_assistant(tmp_db_path, gemma)
    orch = AgentOrchestrator(assistant._db, assistant, gemma)  # type: ignore[arg-type]

    reply = orch.run("안녕", intent=CommandKind.GENERAL_CHAT)

    assert reply.startswith("Iris:")
    assert "안녕" in reply or "도와" in reply
    assert len(gemma.calls) >= 2  # planner + finalize


def test_orchestrator_app_launch_runs_without_approval(tmp_db_path: Path) -> None:
    planner = """
    {
      "goal": "앱 실행",
      "steps": [
        {"tool": "safety_check", "args": {}},
        {"tool": "intent_route", "args": {}},
        {"tool": "assistant_dispatch", "args": {}},
        {"tool": "gemma_finalize", "args": {"only_if_no_direct_reply": true}}
      ]
    }
    """
    gemma = _FakeGemma(planner)
    assistant = _make_assistant(tmp_db_path, gemma)
    orch = AgentOrchestrator(assistant._db, assistant, gemma)  # type: ignore[arg-type]

    reply = orch.run("Cursor 열어줘", intent=CommandKind.APP_LAUNCH)

    assert "실행할까요" not in reply
    assert "Cursor" in reply or "실행" in reply
    assert assistant.ctx.step.name == "NONE"


def test_orchestrator_search_delegate(tmp_db_path: Path) -> None:
    gemma = _FakeGemma('{"goal":"검색","steps":[{"tool":"intent_route","args":{}}]}')
    assistant = _make_assistant(tmp_db_path, gemma)
    registry = ToolRegistry(assistant, gemma)  # type: ignore[arg-type]
    ctx = ToolRunContext(user_text="요즘 영화 뭐 있어", intent=CommandKind.MOVIE_SEARCH)
    result = registry.execute(PlanStep("intent_route"), ctx)
    assert result.direct_reply == AgentOrchestrator.DELEGATE_SEARCH


def test_safety_block_stops_loop(tmp_db_path: Path) -> None:
    gemma = _FakeGemma(
        '{"goal":"x","steps":[{"tool":"safety_check","args":{}},{"tool":"gemma_finalize","args":{}}]}'
    )
    assistant = _make_assistant(tmp_db_path, gemma)
    orch = AgentOrchestrator(assistant._db, assistant, gemma)  # type: ignore[arg-type]
    reply = orch.run("비밀번호 입력해줘")
    assert "차단" in reply
