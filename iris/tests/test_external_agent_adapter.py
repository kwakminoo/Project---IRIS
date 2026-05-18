"""external_agent_adapter — subprocess mock."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from iris.assistant.external_agent_adapter import (
    ExternalAgentResult,
    HermesBackend,
    OpenClawBackend,
    build_external_backend,
    run_external_delegate,
    tier4_delegate_active,
    user_facing_tier4_line,
)
from iris.assistant.openclaw_adapter import OpenClawActionBackend
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.config.settings import Settings, load_settings
from iris.storage.database import Database


def _minimal_settings(tmp_path: Path, **kwargs: object) -> Settings:
    from dataclasses import replace

    p = tmp_path / "test.env"
    p.write_text("", encoding="utf-8")
    base = load_settings(p)
    return replace(base, **kwargs)  # type: ignore[arg-type]


@patch("iris.assistant.openclaw_adapter.subprocess.run")
def test_openclaw_backend_execute_task(mock_run: MagicMock, tmp_path: Path) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="internal cli ok", stderr="")
    fake_cli = tmp_path / "openclaw_fake"
    fake_cli.touch()
    inner = OpenClawActionBackend(
        enabled=True,
        cli_path=str(fake_cli),
        session_id="t",
        timeout_seconds=30,
    )
    oc = OpenClawBackend(inner)
    r, ms = run_external_delegate(oc, goal="테스트 목표", context="ctx")
    assert r.success
    assert r.backend_id == "openclaw"
    assert ms >= 0
    mock_run.assert_called_once()


@patch("iris.assistant.external_agent_adapter.subprocess.run")
def test_hermes_backend_unavailable_when_cli_missing(mock_run: MagicMock) -> None:
    hb = HermesBackend(cli_path="__no_such_hermes_exe__", timeout_seconds=10)
    assert not hb.is_available()
    mock_run.assert_not_called()


def test_tier4_delegate_active_respects_none(tmp_path: Path) -> None:
    s = _minimal_settings(
        tmp_path,
        external_agent_fallback_enabled=True,
        external_agent_backend="none",
    )
    assert not tier4_delegate_active(s)


def test_build_external_backend_openclaw(tmp_path: Path) -> None:
    s = _minimal_settings(tmp_path, external_agent_backend="openclaw")
    b = build_external_backend(s)
    assert b is not None
    assert b.backend_id == "openclaw"


def test_user_facing_line() -> None:
    assert "Iris" in user_facing_tier4_line(True)


class _MockT4:
    backend_id = "openclaw"

    def is_available(self) -> bool:
        return True

    def execute_task(self, goal: str, context: str) -> ExternalAgentResult:
        return ExternalAgentResult(True, "RAW_SECRET_LOG", self.backend_id)


class _G:
    def chat(self, messages: list[object]) -> str:
        c0 = getattr(messages[0], "content", "") if messages else ""
        if "내부 보조 실행 로그" in c0:
            return "Iris가 요청을 마쳤습니다."
        return '{"tool": "list_open_windows", "params": {}, "reason": "루프"}'


def _perceive_result() -> AutomationToolResult:
    return AutomationToolResult(
        True,
        "perceive: ok | win",
        '{"perception_source":"uia"}',
    )


def test_max_steps_triggers_fallback_when_enabled(tmp_path: Path) -> None:
    """로컬 max_steps 초과 시 Tier4(mock) 호출 — raw 로그는 사용자 메시지에 없음."""
    settings = _minimal_settings(
        tmp_path,
        external_agent_fallback_enabled=True,
        external_agent_backend="openclaw",
    )
    db_path = tmp_path / "cu.db"
    db = Database(path=db_path)
    assistant = IrisAssistant(
        db,
        ActionExecutor(db, {}, settings=settings),
        _G(),
        {},
        settings,
    )
    registry = assistant._executor.tool_registry

    def _run(name: str, ctx: object) -> AutomationToolResult:
        if name == "perceive_desktop":
            return _perceive_result()
        return AutomationToolResult(True, "ok", "w")

    registry.run = _run  # type: ignore[method-assign]

    agent = ComputerUseAgent(
        assistant,
        assistant.gemma_client,
        registry,
        max_steps=3,
        tier4_backend=_MockT4(),
    )
    msg = agent.run("반복")
    assert "RAW_SECRET_LOG" not in msg
    assert "마쳤" in msg or "처리" in msg or "확인" in msg


def test_max_steps_no_fallback_when_disabled(tmp_path: Path) -> None:
    settings = _minimal_settings(
        tmp_path,
        external_agent_fallback_enabled=False,
        external_agent_backend="openclaw",
    )
    db_path = tmp_path / "cu2.db"
    db = Database(path=db_path)
    assistant = IrisAssistant(
        db,
        ActionExecutor(db, {}, settings=settings),
        _G(),
        {},
        settings,
    )
    registry = assistant._executor.tool_registry

    def _run(name: str, ctx: object) -> AutomationToolResult:
        if name == "perceive_desktop":
            return _perceive_result()
        return AutomationToolResult(True, "ok", "w")

    registry.run = _run  # type: ignore[method-assign]

    agent = ComputerUseAgent(
        assistant,
        assistant.gemma_client,
        registry,
        max_steps=3,
        tier4_backend=_MockT4(),
    )
    msg = agent.run("반복")
    assert "단계 제한" in msg
