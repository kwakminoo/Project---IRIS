"""모니터링 대화 제안 문장."""

from iris.monitoring.dialogue_bridge import monitoring_proposal_message


def test_approval_waiting_proposal() -> None:
    msg = monitoring_proposal_message("APPROVAL_WAITING", "터미널", "y 입력")
    assert "승인" in msg
    assert "터미널" in msg


def test_stalled_proposal() -> None:
    msg = monitoring_proposal_message("TASK_STALLED", "Cursor", "120초간 변화 없음")
    assert "멈춘" in msg or "이어서" in msg
