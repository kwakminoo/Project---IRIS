"""실행 플랜 생성 (앱 실행 + 레이아웃)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from iris.config.preset_modes import LayoutHint, PresetMode


@dataclass
class LaunchStep:
    app_key: str


@dataclass
class LayoutStep:
    app_key: str
    hint: LayoutHint


@dataclass
class TaskPlan:
    launches: List[LaunchStep]
    layouts: List[LayoutStep]


def plan_from_preset(preset: PresetMode) -> TaskPlan:
    """프리셋에서 순차 실행 플랜 생성."""
    launches = [LaunchStep(k) for k in preset.suggested_app_keys]
    layouts = []
    hints = list(preset.layout_hints)
    for i, k in enumerate(preset.suggested_app_keys):
        hint = hints[i] if i < len(hints) else hints[-1]
        layouts.append(LayoutStep(k, hint))
    return TaskPlan(launches=launches, layouts=layouts)
