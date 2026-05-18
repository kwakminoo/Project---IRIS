"""모니터링 이벤트 → 대화 제안 문장."""

from __future__ import annotations


def monitoring_proposal_message(
    category: str,
    title: str,
    recommended: str,
    alert_message: str = "",
) -> str:
    """자연어 제안 (실행은 승인 후)."""
    rec = (recommended or "").strip()
    base = alert_message.strip()[:300] if alert_message else ""

    if category == "APPROVAL_WAITING":
        return (
            f"모니터링: '{title}'에서 승인 입력이 필요해 보입니다. "
            f"{rec or '터미널 확인'} — 진행하려면 '승인'이라고 말씀해 주세요."
        )
    if category == "ERROR_DETECTED":
        return (
            f"모니터링: '{title}'에서 오류가 감지되었습니다. "
            f"{rec or base or '로그를 확인해 보시겠어요?'}"
        )
    if category == "TASK_STALLED":
        return (
            f"모니터링: '{title}' 작업이 {rec or '한동안 멈춘 것 같습니다'}. "
            "이어서 진행할까요?"
        )
    if category == "RESPONSE_READY":
        return (
            f"모니터링: '{title}' 탭에서 응답이 준비된 것 같습니다. "
            f"{rec or '확인해 보시겠어요?'}"
        )
    if category == "USER_ACTION_REQUIRED":
        return (
            f"모니터링: '{title}'에서 직접 조치가 필요합니다. "
            f"{rec or base}"
        )
    if category == "GENERATION_FAILED":
        return f"모니터링: '{title}' 생성이 실패한 것 같습니다. {rec or '재시도를 검토해 주세요.'}"
    return base or f"모니터링: '{title}' 상태 변경 ({category})."
