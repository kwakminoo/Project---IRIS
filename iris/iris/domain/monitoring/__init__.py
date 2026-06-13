"""모니터링 도메인 확장 필드."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskMonitoringLink:
    """MonitoringEvent와 Task 연계."""

    related_task_id: str | None = None
    related_plan_step_id: str | None = None
    related_action_attempt_id: str | None = None
