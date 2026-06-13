"""Task·Plan·Step 상태 Enum."""

from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    """작업 유형."""

    COMPUTER_USE = "computer_use"
    AUTOMATION = "automation"
    COMPOSITE = "composite"
    CHAT = "chat"


class TaskStatus(str, Enum):
    """Task 생명주기 상태."""

    DRAFT = "draft"
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_USER = "waiting_user"
    WAITING_RESOURCE = "waiting_resource"
    SUSPENDED = "suspended"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """작업 우선순위."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class StepStatus(str, Enum):
    """PlanStep 실행 상태."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AttemptStatus(str, Enum):
    """ActionAttempt 상태."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
