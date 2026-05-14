"""감지 결과 → 한국어 알림 (Gemma 선택)."""

from __future__ import annotations

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.monitoring.models import DetectionResult, StatusCategory


def template_message(result: DetectionResult, target_title: str) -> str:
    """로컬 LLM 없을 때 템플릿."""
    cat = result.category
    if cat == StatusCategory.APPROVAL_WAITING:
        return (
            f"[{target_title}] 승인 입력을 기다리는 중입니다. "
            f"{result.recommended_action or '터미널에서 y/n 등을 확인하세요.'}"
        )
    if cat == StatusCategory.ERROR_DETECTED:
        return f"[{target_title}] 오류 가능성이 있습니다: {result.reason}"
    if cat == StatusCategory.GENERATION_FAILED:
        return f"[{target_title}] 이미지/생성 작업이 실패했을 수 있습니다. 재시도를 검토하세요."
    if cat == StatusCategory.TASK_STALLED:
        return f"[{target_title}] 진행이 멈춘 것으로 보입니다. {result.reason}"
    if cat == StatusCategory.RESPONSE_READY:
        return f"[{target_title}] 응답이 준비된 것으로 보입니다. 탭에서 확인하세요."
    if cat == StatusCategory.BUILD_NOT_STARTED:
        return f"[{target_title}] 빌드/실행이 아직 없을 수 있습니다. IDE에서 확인하세요."
    if cat == StatusCategory.USER_ACTION_REQUIRED:
        return f"[{target_title}] 사용자 직접 조치가 필요할 수 있습니다."
    return f"[{target_title}] {result.reason}"


def build_alert_text(
    gemma: GemmaClient | None,
    result: DetectionResult,
    target_title: str,
) -> str:
    """Gemma 가능 시 한 줄 요약, 아니면 템플릿."""
    base = template_message(result, target_title)
    if gemma is None or result.category in (StatusCategory.NORMAL, StatusCategory.UNKNOWN):
        return base
    try:
        prompt = (
            "다음 모니터링 알림을 사용자에게 보여줄 한 문장 한국어로 짧게 다듬어줘. "
            "따옴표 없이 한 문장만.\n"
            f"{base}"
        )
        refined = gemma.chat(
            [
                ChatMessage("system", "You output one short Korean sentence only."),
                ChatMessage("user", prompt),
            ]
        )
        if refined and len(refined) < 400:
            return refined.strip()
    except Exception:
        pass
    return base
