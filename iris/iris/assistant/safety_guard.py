"""Safety Guard — 위험 행동 차단."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class ActionCategory(Enum):
    FILE_DELETE = auto()
    PAYMENT = auto()
    PASSWORD = auto()
    PII_SUBMIT = auto()
    SYSTEM_SETTINGS = auto()
    SHELL_DANGEROUS = auto()
    INPUT_UNAPPROVED = auto()
    SAFE = auto()


_DANGER_PATTERNS: list[tuple[ActionCategory, re.Pattern[str]]] = [
    (
        ActionCategory.FILE_DELETE,
        re.compile(r"(삭제|지워|rm\s+-rf|format\s+c:|드라이브\s*포맷)", re.IGNORECASE),
    ),
    (ActionCategory.PAYMENT, re.compile(r"(결제|카드\s*번호|송금)", re.IGNORECASE)),
    (ActionCategory.PASSWORD, re.compile(r"(비밀번호|password\s*입력)", re.IGNORECASE)),
    (ActionCategory.PII_SUBMIT, re.compile(r"(주민번호|여권번호|계좌\s*번호)", re.IGNORECASE)),
    (ActionCategory.SYSTEM_SETTINGS, re.compile(r"(레지스트리|그룹\s*정책|방화벽\s*끄)", re.IGNORECASE)),
    (
        ActionCategory.SHELL_DANGEROUS,
        re.compile(r"(curl\s+\|?\s*bash|powershell\s+-enc|format\s+volume)", re.IGNORECASE),
    ),
    (
        ActionCategory.INPUT_UNAPPROVED,
        re.compile(r"(마우스\s*클릭|키보드\s*입력\s*해|pyautogui\.click)", re.IGNORECASE),
    ),
]


@dataclass
class ActionRequest:
    """검사 대상 행동 설명."""

    summary: str
    approved: bool = False


@dataclass
class SafetyResult:
    allowed: bool
    reason: str


def evaluate(action: ActionRequest) -> SafetyResult:
    """명시적 위험 패턴만 차단. 실행 승인은 호출 측에서 처리."""
    text = action.summary
    for cat, pat in _DANGER_PATTERNS:
        if pat.search(text):
            return SafetyResult(False, f"차단: {cat.name}")
    return SafetyResult(True, "허용")


def quick_block_user_text(text: str) -> Optional[str]:
    """채팅 입력만으로 즉시 차단할 위험 키워드."""
    fake = ActionRequest(summary=text, approved=False)
    r = evaluate(fake)
    if not r.allowed and "차단" in r.reason:
        return r.reason
    return None
