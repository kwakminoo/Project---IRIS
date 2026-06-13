"""SQLite Task Runtime Repository 테스트."""

from pathlib import Path

from iris.application.runtime_factory import build_task_runtime
from iris.automation.tool_registry import AutomationToolRegistry
from iris.domain.task.enums import TaskStatus, TaskType
from iris.domain.task.models import TaskCheckpoint
from iris.domain.shared.id_generator import new_id
from iris.storage.database import Database


def test_task_save_and_load(tmp_path: Path):
    db = Database(tmp_path / "task.db")
    repos = build_task_runtime(db, AutomationToolRegistry(db)).repos
    from iris.domain.task.models import Task

    task = Task(
        id=new_id(),
        task_type=TaskType.COMPUTER_USE,
        title="build",
        goal="build iris",
        status=TaskStatus.QUEUED,
    )
    repos.tasks.save(task)
    loaded = repos.tasks.get_by_id(task.id)
    assert loaded is not None
    assert loaded.goal == "build iris"


def test_plan_and_steps_persist(tmp_path: Path):
    db = Database(tmp_path / "plan.db")
    runtime = build_task_runtime(db, AutomationToolRegistry(db))
    task = runtime.tasks.create_task_from_cu_request("open notepad")
    plan, steps = runtime.tasks.on_plan_created(
        task,
        steps=[("launch", "computer.launch_app", "launch_app", {"app_key": "notepad"})],
    )
    loaded_plan = runtime.repos.plans.get_plan(plan.id)
    assert loaded_plan is not None
    loaded_steps = runtime.repos.plans.get_steps(plan.id)
    assert len(loaded_steps) == 1
    assert loaded_steps[0].title == "launch"


def test_checkpoint_restore(tmp_path: Path):
    db = Database(tmp_path / "cp.db")
    runtime = build_task_runtime(db, AutomationToolRegistry(db))
    task = runtime.tasks.create_task_from_cu_request("resume test")
    cp = TaskCheckpoint(
        id=new_id(),
        task_id=task.id,
        plan_version=1,
        snapshot={"goal": "resume test", "step": 2},
    )
    runtime.repos.checkpoints.save(cp)
    latest = runtime.repos.checkpoints.get_latest_for_task(task.id)
    assert latest is not None
    assert latest.snapshot.get("step") == 2


def test_schema_migrations_applied(tmp_path: Path):
    db = Database(tmp_path / "mig.db")
    row = db._execute(
        "SELECT version FROM schema_migrations ORDER BY applied_at"
    ).fetchall()
    versions = [r[0] for r in row]
    assert "001_create_task_runtime" in versions
    assert "003_create_approval_records" in versions
