"""Phase 1 — Task Runtime 주입·ComputerUseAgent 생성."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter


def _assistant(tmp_path: Path):
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.storage.database import Database

    db = Database(tmp_path / "p1.db")
    executor = MagicMock()
    from iris.automation.tool_registry import AutomationToolRegistry

    executor.tool_registry = AutomationToolRegistry(db)
    gemma = MagicMock()
    return IrisAssistant(db, executor, gemma, {}, MagicMock())


def test_iris_assistant_can_construct_computer_use_agent(tmp_path: Path):
    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    assert isinstance(agent, ComputerUseAgent)


def test_computer_use_agent_accepts_task_runtime(tmp_path: Path):
    assistant = _assistant(tmp_path)
    adapter = assistant._ensure_task_runtime()
    assert adapter is not None
    assert isinstance(adapter, CuTaskAdapter)

    agent = assistant._create_computer_use_agent()
    assert agent._task_runtime is adapter
    assert agent._task_runtime is assistant._cu_task_adapter


def test_computer_use_agent_without_runtime_keeps_legacy_compatibility(tmp_path: Path):
    from iris.automation.tool_registry import AutomationToolRegistry
    from iris.storage.database import Database

    db = Database(tmp_path / "legacy.db")
    registry = AutomationToolRegistry(db)
    assistant = MagicMock()
    assistant._db = db
    assistant._app_paths = {}
    assistant._settings = MagicMock()

    agent = ComputerUseAgent(assistant, MagicMock(), registry, max_steps=5)
    assert agent._task_runtime is None

    # task_runtime 없이도 run() 진입 가능 (빈 goal은 즉시 반환)
    msg = agent.run("")
    assert "비어" in msg
