"""작업 모드 멘트·프리셋 매핑."""

from __future__ import annotations

import re

from iris.config.preset_modes import WORK_PRESETS, PresetMode


def work_entry_message(recent_block: str) -> str:
    return (
        "Iris: 어떤 작업을 실행할까요? 최근 작업을 이어갈까요, 새로운 작업인가요?\n" + recent_block
    )


def match_work_preset(user_text: str) -> PresetMode:
    """사용자 발화에서 작업 유형 추정."""
    t = user_text.lower()
    if re.search(r"개발|iris|코드|cursor", t):
        return WORK_PRESETS[0]
    if re.search(r"문서|한글|word", t):
        return WORK_PRESETS[1]
    if re.search(r"발표|ppt|파워포인트", t):
        return WORK_PRESETS[2]
    if re.search(r"ai|챗|미드저니|discord", t):
        return WORK_PRESETS[3]
    if re.search(r"검색|조사|자료", t):
        return WORK_PRESETS[4]
    return WORK_PRESETS[0]


def propose_work_apps_message(preset: PresetMode) -> str:
    apps = ", ".join(preset.suggested_app_keys)
    return f"Iris: {preset.title}에 맞춰 {apps} 를 열고 기본 배치로 정리할까요?"
