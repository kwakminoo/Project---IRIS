"""state_detector 규칙 스모크 테스트."""

from iris.monitoring.models import StatusCategory, TargetType
from iris.monitoring.state_detector import detect_state


def test_proceed_yn():
    r = detect_state(
        TargetType.TERMINAL_COMMAND,
        "npm install\nProceed? (y/n)\n",
        StatusCategory.NORMAL,
        "a",
        "b",
        None,
        stall_seconds=9999,
    )
    assert r.category == StatusCategory.APPROVAL_WAITING


def test_permission_denied():
    r = detect_state(
        TargetType.TERMINAL_COMMAND,
        "permission denied\n",
        StatusCategory.NORMAL,
        "a",
        "b",
        None,
        stall_seconds=9999,
    )
    assert r.category == StatusCategory.ERROR_DETECTED
