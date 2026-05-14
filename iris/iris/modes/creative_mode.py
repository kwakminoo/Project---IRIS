"""창작 모드 멘트·프리셋 매핑."""

from __future__ import annotations

import re

from iris.config.preset_modes import CREATIVE_PRESETS, PresetMode


def creative_entry_message() -> str:
    return "Iris: 어떤 창작 작업인가요? (이미지 / 영상 / 디자인)"


def match_creative_preset(user_text: str) -> PresetMode:
    t = user_text.lower()
    if re.search(r"이미지|미드저니|mj", t):
        return CREATIVE_PRESETS[0]
    if re.search(r"영상|프리미어|캡컷|premiere|capcut", t):
        return CREATIVE_PRESETS[1]
    if re.search(r"디자인|피그마|포토샵|figma|psd", t):
        return CREATIVE_PRESETS[2]
    return CREATIVE_PRESETS[0]


def propose_creative_apps_message(preset: PresetMode) -> str:
    apps = ", ".join(preset.suggested_app_keys)
    return f"Iris: {preset.title}에 맞춰 {apps} 를 열고 기본 배치로 정리할까요?"
