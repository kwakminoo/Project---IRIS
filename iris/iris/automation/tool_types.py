"""자동화 도구 공통 타입."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class RiskLevel(Enum):
    """도구 위험 등급."""

    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL_RISK = "CRITICAL_RISK"


@dataclass
class AutomationToolContext:
    """도구 실행 컨텍스트."""

    params: Dict[str, Any] = field(default_factory=dict)
    approved: bool = False
    auto_approve_low_risk: bool = False  # 레거시 필드: 현재는 3단계까지 기본 자동 허용
    app_paths: Dict[str, str] = field(default_factory=dict)
    settings: Any = None  # iris.config.settings.Settings (순환 import 방지)
    summary: str = ""


@dataclass
class AutomationToolResult:
    """도구 실행 결과."""

    success: bool
    message: str
    detail: str | None = None


def requires_approval_for(risk: RiskLevel, auto_approve_low_risk: bool) -> bool:
    """1~3단계(LOW/MEDIUM/HIGH)는 자동 허용, 4단계(CRITICAL)는 승인 필요."""
    return risk is RiskLevel.CRITICAL_RISK
