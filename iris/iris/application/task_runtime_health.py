"""Task Runtime 초기화·동작 상태."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from iris.domain.shared.time import utc_now_iso

HealthStatus = Literal["healthy", "degraded", "failed"]


@dataclass
class TaskRuntimeHealth:
    """Task Runtime health — silent fallback 방지용."""

    status: HealthStatus = "healthy"
    error_type: str | None = None
    error_message: str | None = None
    occurred_at: str | None = None
    legacy_fallback: bool = False

    def mark_failed(self, exc: BaseException) -> None:
        self.status = "failed"
        self.error_type = type(exc).__name__
        self.error_message = str(exc)[:500]
        self.occurred_at = utc_now_iso()

    def mark_degraded(self, message: str) -> None:
        self.status = "degraded"
        self.error_message = message[:500]
        self.occurred_at = utc_now_iso()
        self.legacy_fallback = True


# 전역 health (AgentAdapter lazy init 시 갱신)
_runtime_health = TaskRuntimeHealth()


def get_task_runtime_health() -> TaskRuntimeHealth:
    return _runtime_health


def reset_task_runtime_health() -> None:
    global _runtime_health
    _runtime_health = TaskRuntimeHealth()
