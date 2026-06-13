"""CuTaskAdapter 단위 테스트."""

from pathlib import Path
from unittest.mock import MagicMock

from iris.application.runtime_factory import build_task_runtime
from iris.automation.tool_registry import AutomationToolRegistry
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter
from iris.storage.database import Database


def test_cu_adapter_creates_task_on_start(tmp_path: Path):
    db = Database(tmp_path / "cu.db")
    runtime = build_task_runtime(db, AutomationToolRegistry(db))
    adapter = CuTaskAdapter(runtime)
    tid = adapter.on_cu_started("build project", {"app_key": "code"})
    assert tid
    assert adapter.task_id == tid
    loaded = runtime.repos.tasks.get_by_id(tid)
    assert loaded is not None
    assert loaded.goal == "build project"


def test_cu_adapter_full_plan_steps(tmp_path: Path):
    db = Database(tmp_path / "cu2.db")
    runtime = build_task_runtime(db, AutomationToolRegistry(db))
    adapter = CuTaskAdapter(runtime)
    adapter.on_cu_started("plan test", None)

    item = MagicMock()
    item.tool = "launch_app"
    item.params = {"app_key": "notepad"}
    item.reason = "open notepad"
    item.index = 0
    adapter.on_full_plan_created([item])

    task = runtime.repos.tasks.get_by_id(adapter.task_id or "")
    assert task and task.active_plan_id
    steps = runtime.repos.plans.get_steps(task.active_plan_id)
    assert len(steps) == 1
