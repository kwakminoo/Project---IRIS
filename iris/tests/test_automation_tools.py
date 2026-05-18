"""AutomationToolRegistry·승인·로깅 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolContext, RiskLevel, requires_approval_for
from iris.automation.tools import all_automation_tools
from iris.storage.database import Database


def test_all_tools_registered() -> None:
    reg = AutomationToolRegistry()
    names = reg.list_tools()
    expected = {t.name for t in all_automation_tools()}
    assert set(names) == expected
    assert len(names) == 9


def test_risk_approval_rules() -> None:
    assert requires_approval_for(RiskLevel.LOW_RISK, False) is False
    assert requires_approval_for(RiskLevel.LOW_RISK, True) is False
    assert requires_approval_for(RiskLevel.MEDIUM_RISK, False) is False
    assert requires_approval_for(RiskLevel.HIGH_RISK, False) is False
    assert requires_approval_for(RiskLevel.CRITICAL_RISK, True) is True


def test_low_risk_runs_without_setting(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "t.db")
    reg = AutomationToolRegistry(db)
    ctx = AutomationToolContext(params={}, approved=False, auto_approve_low_risk=False)
    assert reg.needs_approval("list_open_windows", ctx) is False
    res = reg.run("list_open_windows", ctx)
    assert "승인" not in res.message


def test_high_risk_auto_runs_by_policy(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "t2.db")
    reg = AutomationToolRegistry(db)
    ctx = AutomationToolContext(
        params={"text": "hello"},
        approved=False,
        auto_approve_low_risk=False,
    )
    assert reg.needs_approval("type_text", ctx) is False


def test_run_shell_still_requires_approval(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "t3.db")
    reg = AutomationToolRegistry(db)
    ctx = AutomationToolContext(
        params={"command": "echo hi"},
        approved=False,
        auto_approve_low_risk=True,
    )
    res = reg.run("run_shell", ctx)
    assert res.success is False
    assert "승인" in res.message


def test_run_shell_dangerous_pattern(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "t4.db")
    reg = AutomationToolRegistry(db)
    ctx = AutomationToolContext(
        params={"command": "rm -rf /"},
        approved=True,
        auto_approve_low_risk=True,
    )
    res = reg.run("run_shell", ctx)
    assert res.success is False
    assert "차단" in res.message


def test_assistant_automation_approval_flow(tmp_path: Path) -> None:
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.automation.action_executor import ActionExecutor
    from iris.core.context_manager import DialogueStep

    db = Database(path=tmp_path / "t6.db")
    executor = ActionExecutor(db, {})
    assistant = IrisAssistant(db, executor, object(), {})  # type: ignore[arg-type]
    reply = assistant.request_automation_tool(
        "launch_app",
        {"app_key": "code", "display_name": "Cursor"},
        "앱 실행 테스트",
    )
    assert "실행할까요" not in reply
    assert assistant.ctx.step is DialogueStep.NONE
    assert assistant.ctx.pending_automation is None


def test_tool_log_written(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "t5.db")
    db.set_auto_approve_low_risk(True)
    reg = AutomationToolRegistry(db)
    ctx = AutomationToolContext(params={}, approved=False, auto_approve_low_risk=True)
    reg.run("list_open_windows", ctx)
    row = db._conn.execute("SELECT COUNT(*) AS c FROM automation_tool_logs").fetchone()
    assert int(row["c"]) >= 1
