"""Task·PlanStep 도메인 상태 전이 테스트."""

from iris.domain.task.enums import StepStatus, TaskStatus, TaskType
from iris.domain.task.models import Plan, PlanStep, Task
from iris.domain.task.transitions import can_transition_task


def test_task_valid_transition_running_to_waiting_approval():
    task = Task(
        id="t1",
        task_type=TaskType.COMPUTER_USE,
        title="build",
        goal="build project",
        status=TaskStatus.RUNNING,
    )
    result = task.transition_to(TaskStatus.WAITING_APPROVAL)
    assert result.ok
    assert result.value.status == TaskStatus.WAITING_APPROVAL


def test_task_invalid_transition_completed_to_running():
    task = Task(
        id="t1",
        task_type=TaskType.COMPUTER_USE,
        title="x",
        goal="x",
        status=TaskStatus.COMPLETED,
    )
    result = task.transition_to(TaskStatus.RUNNING)
    assert not result.ok


def test_plan_revision_increments_version():
    plan = Plan(id="p1", task_id="t1", version=1)
    rev = plan.create_revision("repair failed")
    assert rev.version == 2
    assert rev.revision_reason == "repair failed"


def test_plan_step_mark_succeeded():
    step = PlanStep(
        id="s1",
        plan_id="p1",
        index=0,
        title="launch",
        capability_required="computer.launch_app",
    )
    done = step.mark_succeeded()
    assert done.status == StepStatus.SUCCEEDED


def test_can_transition_task_approval_resume():
    assert can_transition_task(TaskStatus.WAITING_APPROVAL, TaskStatus.RUNNING)
