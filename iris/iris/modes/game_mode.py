"""게임 모드 멘트·프리셋 매핑."""

from __future__ import annotations

import re

from iris.config.preset_modes import GAME_PRESETS, PresetMode


def game_entry_message() -> str:
    return (
        "Iris: 어떤 게임을 실행할까요? 최근에는 리그 오브 레전드와 스팀 게임을 실행했습니다."
    )


def match_game_preset(user_text: str) -> PresetMode:
    t = user_text.lower()
    if re.search(r"롤|리그|lol|league", t):
        return GAME_PRESETS[0]
    if re.search(r"스팀|steam", t):
        return GAME_PRESETS[1]
    if re.search(r"방송|obs|녹화", t):
        return GAME_PRESETS[2]
    return GAME_PRESETS[0]


def propose_side_apps_message(preset: PresetMode) -> str:
    if preset.id == "game_lol":
        return "Iris: 롤 클라이언트, Discord, 유튜브 음악, OP.GG 를 함께 열까요? (브라우저로 OP.GG)"
    if preset.id == "game_steam":
        return "Iris: Steam, Discord, Chrome 을 함께 열까요?"
    return "Iris: OBS, Discord, Chrome 을 함께 열까요?"
