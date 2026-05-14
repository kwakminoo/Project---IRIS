"""동적 프리셋: 작업/게임/창작 유형별 기본 앱·레이아웃 힌트."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Sequence


class PresetCategory(str, Enum):
    WORK = "work"
    GAME = "game"
    CREATIVE = "creative"


@dataclass(frozen=True)
class LayoutHint:
    """모니터 인덱스와 영역 비율(0~1)."""

    monitor_index: int = 0
    left: float = 0.0
    top: float = 0.0
    width: float = 0.5
    height: float = 1.0


@dataclass(frozen=True)
class PresetMode:
    """확장 가능한 프리셋 정의."""

    id: str
    category: PresetCategory
    title: str
    suggested_app_keys: Sequence[str]
    layout_hints: Sequence[LayoutHint] = field(default_factory=tuple)


# 앱 키는 app_paths / 실행 시 이름 매핑과 연동 (없으면 스킵)
WORK_PRESETS: List[PresetMode] = [
    PresetMode(
        "work_dev",
        PresetCategory.WORK,
        "개발 작업",
        ("code", "python", "chrome", "discord"),
        (LayoutHint(0, 0, 0, 0.55, 1.0), LayoutHint(0, 0.55, 0, 0.45, 0.5), LayoutHint(0, 0.55, 0.5, 0.45, 0.5)),
    ),
    PresetMode(
        "work_doc",
        PresetCategory.WORK,
        "문서 작업",
        ("chrome", "edge"),
        (LayoutHint(0, 0, 0, 0.6, 1.0), LayoutHint(0, 0.6, 0, 0.4, 1.0)),
    ),
    PresetMode(
        "work_deck",
        PresetCategory.WORK,
        "발표 준비",
        ("chrome", "edge"),
        (LayoutHint(0, 0, 0, 0.7, 1.0), LayoutHint(0, 0.7, 0, 0.3, 1.0)),
    ),
    PresetMode(
        "work_ai",
        PresetCategory.WORK,
        "AI 작업",
        ("chrome", "code", "discord"),
        (LayoutHint(0, 0, 0, 0.34, 1.0), LayoutHint(0, 0.34, 0, 0.33, 1.0), LayoutHint(0, 0.67, 0, 0.33, 1.0)),
    ),
    PresetMode(
        "work_research",
        PresetCategory.WORK,
        "검색/조사",
        ("chrome", "edge"),
        (LayoutHint(0, 0, 0, 1.0, 1.0),),
    ),
]

GAME_PRESETS: List[PresetMode] = [
    PresetMode(
        "game_lol",
        PresetCategory.GAME,
        "리그 오브 레전드",
        ("league", "discord", "chrome", "steam"),
        (LayoutHint(0, 0, 0, 1.0, 1.0),),
    ),
    PresetMode(
        "game_steam",
        PresetCategory.GAME,
        "Steam 게임",
        ("steam", "discord", "chrome"),
        (LayoutHint(0, 0, 0, 1.0, 1.0),),
    ),
    PresetMode(
        "game_stream",
        PresetCategory.GAME,
        "방송/녹화",
        ("obs", "discord", "chrome"),
        (LayoutHint(0, 0, 0, 0.7, 1.0), LayoutHint(0, 0.7, 0, 0.3, 1.0)),
    ),
]

CREATIVE_PRESETS: List[PresetMode] = [
    PresetMode(
        "creative_image",
        PresetCategory.CREATIVE,
        "이미지 작업",
        ("discord", "chrome"),
        (LayoutHint(0, 0, 0, 0.5, 1.0), LayoutHint(0, 0.5, 0, 0.5, 1.0)),
    ),
    PresetMode(
        "creative_video",
        PresetCategory.CREATIVE,
        "영상 작업",
        ("chrome", "edge"),
        (LayoutHint(0, 0, 0, 0.65, 1.0), LayoutHint(0, 0.65, 0, 0.35, 1.0)),
    ),
    PresetMode(
        "creative_design",
        PresetCategory.CREATIVE,
        "디자인 작업",
        ("chrome", "edge"),
        (LayoutHint(0, 0, 0, 0.55, 1.0), LayoutHint(0, 0.55, 0, 0.45, 1.0)),
    ),
]


def all_presets() -> List[PresetMode]:
    return [*WORK_PRESETS, *GAME_PRESETS, *CREATIVE_PRESETS]


def find_preset(preset_id: str) -> PresetMode | None:
    for p in all_presets():
        if p.id == preset_id:
            return p
    return None
