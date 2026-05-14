"""사용자 입력 명령 유형 분류."""

from __future__ import annotations

import re
from enum import Enum, auto


class CommandKind(Enum):
    GENERAL_CHAT = auto()
    LAUNCH_APP = auto()
    WINDOW_CONTROL = auto()
    WEB_OR_REPORT = auto()
    WORK_MODE = auto()
    GAME_MODE = auto()
    CREATIVE_MODE = auto()
    COMPUTER_ACTION = auto()
    MONITORING_STATUS = auto()
    ALERT_COMMAND = auto()


_WORK_PATTERNS = re.compile(
    r"(작업\s*시작|일해야|개발\s*시작|일\s*할게|작업\s*할게|업무\s*시작)",
    re.IGNORECASE,
)
_GAME_PATTERNS = re.compile(
    r"(게임할래|게임\s*할래|롤|배그|게임\s*시작|게임\s*켜)",
    re.IGNORECASE,
)
_CREATIVE_PATTERNS = re.compile(
    r"(이미지\s*작업|영상\s*편집|디자인\s*작업|창작)",
    re.IGNORECASE,
)
_WEB_PATTERNS = re.compile(
    r"(검색해줘|자료\s*찾아|요약해줘|보고서로\s*정리|웹\s*검색)",
    re.IGNORECASE,
)
_MONITOR_PATTERNS = re.compile(r"(모니터링|상태\s*확인|지금\s*뭐\s*해)", re.IGNORECASE)
_ALERT_PATTERNS = re.compile(r"(알림|경고)", re.IGNORECASE)
_DANGER_COMPUTER = re.compile(
    r"(마우스\s*클릭|키보드|쉘\s*실행|rm\s+-rf|포맷|레지스트리\s*삭제)",
    re.IGNORECASE,
)
_LAUNCH = re.compile(r"(실행해줘|켜줘|열어줘|launch|open\s+app)", re.IGNORECASE)


def classify_command(text: str) -> CommandKind:
    """간단 휴리스틱 분류 (한국어 우선)."""
    t = text.strip()
    if not t:
        return CommandKind.GENERAL_CHAT

    if _WORK_PATTERNS.search(t):
        return CommandKind.WORK_MODE
    if _GAME_PATTERNS.search(t):
        return CommandKind.GAME_MODE
    if _CREATIVE_PATTERNS.search(t):
        return CommandKind.CREATIVE_MODE
    if _WEB_PATTERNS.search(t):
        return CommandKind.WEB_OR_REPORT
    if _MONITOR_PATTERNS.search(t):
        return CommandKind.MONITORING_STATUS
    if _ALERT_PATTERNS.search(t):
        return CommandKind.ALERT_COMMAND
    if _DANGER_COMPUTER.search(t):
        return CommandKind.COMPUTER_ACTION
    if _LAUNCH.search(t):
        return CommandKind.LAUNCH_APP

    if "창" in t and ("포커스" in t or "이동" in t or "크기" in t):
        return CommandKind.WINDOW_CONTROL

    return CommandKind.GENERAL_CHAT
