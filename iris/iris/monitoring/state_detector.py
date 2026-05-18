"""텍스트·로그 스니펫 기반 상태 분류."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from iris.monitoring.models import DetectionResult, StatusCategory, TargetType


def _parse_iso(ts: str | None) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_state(
    target_type: TargetType,
    text_snippet: str,
    prev_category: StatusCategory,
    prev_hash: str,
    new_hash: str,
    last_changed_at_iso: str | None,
    stall_seconds: float = 120.0,
) -> DetectionResult:
    """
    규칙 기반 분류. 원문 전체가 아닌 스니펫만 사용.
    """
    low = (text_snippet or "").lower()

    # 승인 대기
    if re.search(r"proceed\?\s*\(y/n\)|proceed\?\s*\[y/n\]", low, re.I):
        return DetectionResult(
            StatusCategory.APPROVAL_WAITING,
            0.92,
            "Proceed? (y/n) 패턴",
            "터미널에 y 또는 n 입력",
        )
    if "do you want to continue" in low:
        return DetectionResult(
            StatusCategory.APPROVAL_WAITING,
            0.88,
            "continue 확인 프롬프트",
            "사용자 확인 후 진행",
        )

    # 생성 실패 (Midjourney/Discord 문맥 우선)
    if re.search(r"generation failed|image generation failed|job failed", low, re.I):
        return DetectionResult(
            StatusCategory.GENERATION_FAILED,
            0.85,
            "generation failed",
            "재시도 또는 프롬프트 수정",
        )
    if re.search(r"\bretry\b", low) and any(
        x in low for x in ("midjourney", "discord", "imagine", "dall-e")
    ):
        return DetectionResult(
            StatusCategory.GENERATION_FAILED,
            0.55,
            "retry + 생성 도구 문맥",
            "재시도 검토",
        )

    # 오류
    if "permission denied" in low:
        return DetectionResult(
            StatusCategory.ERROR_DETECTED,
            0.9,
            "permission denied",
            "권한 확인",
        )
    if re.search(r"\berror\b|\bfailed\b|\bexception\b", low):
        return DetectionResult(
            StatusCategory.ERROR_DETECTED,
            0.65,
            "error/failed/exception 키워드",
            "로그 확인",
        )

    # 응답 완료 (챗봇 탭)
    if target_type == TargetType.BROWSER_TAB:
        if any(
            x in low
            for x in (
                "copy code",
                "코드 복사",
                "regenerate",
                "다시 생성",
            )
        ) and len(low) > 80:
            return DetectionResult(
                StatusCategory.RESPONSE_READY,
                0.6,
                "응답 완료 휴리스틱",
                "탭에서 응답 확인",
            )

    # 빌드 미실행 (IDE)
    if target_type == TargetType.DESKTOP_WINDOW:
        if ("build" in low or "빌드" in text_snippet) and any(
            x in low for x in ("run", "debug", "실행", "start debugging")
        ):
            if "succeeded" not in low and "성공" not in text_snippet:
                return DetectionResult(
                    StatusCategory.BUILD_NOT_STARTED,
                    0.5,
                    "빌드/실행 버튼 문맥",
                    "빌드 또는 실행 시작 검토",
                )

    # 사용자 조치 필요
    if any(
        x in low
        for x in (
            "captcha",
            "verify you are human",
            "로그인이 필요",
            "sign in to continue",
        )
    ):
        return DetectionResult(
            StatusCategory.USER_ACTION_REQUIRED,
            0.75,
            "인증/로그인 문맥",
            "브라우저에서 직접 처리",
        )

    # 정체: 해시 동일 + 시간 경과
    changed = _parse_iso(last_changed_at_iso)
    now_cmp = datetime.utcnow()
    if changed is not None and changed.tzinfo is not None:
        changed = changed.replace(tzinfo=None)

    if (
        prev_hash
        and new_hash
        and prev_hash == new_hash
        and len(new_hash) > 8
        and changed is not None
    ):
        age = (now_cmp - changed).total_seconds()
        if age > stall_seconds and prev_category in (
            StatusCategory.NORMAL,
            StatusCategory.UNKNOWN,
            StatusCategory.RESPONSE_READY,
        ):
            return DetectionResult(
                StatusCategory.TASK_STALLED,
                0.55,
                f"{int(age)}초간 변화 없음",
                "작업 진행 여부 확인",
            )

    if not low.strip():
        return DetectionResult(StatusCategory.UNKNOWN, 0.2, "수집 텍스트 없음", "")

    return DetectionResult(StatusCategory.NORMAL, 0.5, "특이 패턴 없음", "")


def category_needs_dialogue(category: StatusCategory) -> bool:
    """대화/UI에 제안을 띄울 카테고리."""
    return category not in (StatusCategory.NORMAL, StatusCategory.UNKNOWN)
