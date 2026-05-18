"""LLM 승인 분류 — pending_cu·자동화 승인 후속 발화 해석."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from iris.ai.gemma_client import ChatMessage, GemmaClient, FALLBACK_KO
from iris.ai.response_parser import extract_json_object

APPROVAL_CLASSIFIER_SYSTEM = """이전에 Iris가 실행 확인을 요청한 맥락에서 사용자 답만 분석하세요. JSON만 출력.

스키마: { "decision": "approve | reject | clarify | unrelated", "confidence": 0.0-1.0 }

approve: 진행해줘, 그래, 해줘, 보내, 응, 승인, ok, yes 등 실행 동의
reject: 취소, 아니, 하지마, no 등 거절
clarify: 승인/거절이 아닌 짧은 되묻기·애매한 답
unrelated: 완전히 다른 주제·새 작업 요청

다른 텍스트 없이 JSON만.
"""

_APPROVE_EXACT = frozenset(
    {"응", "네", "좋아", "승인", "실행", "확인", "yes", "ok", "y", "ㅇㅇ"}
)
_REJECT_EXACT = frozenset({"아니", "취소", "no", "n", "싫어"})

_APPROVE_SUBSTR = (
    "진행해",
    "진행 해",
    "해줘",
    "해 줘",
    "그래",
    "보내",
    "승인",
    "실행해",
    "ok",
    "okay",
)
_REJECT_SUBSTR = ("취소", "하지마", "하지 마", "안 할", "안할", "거절", "싫어")


class FollowupDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    CLARIFY = "clarify"
    UNRELATED = "unrelated"


@dataclass(frozen=True)
class FollowupClassification:
    decision: FollowupDecision
    confidence: float = 1.0


def is_rule_approval(text: str) -> bool:
    """규칙 기반 승인 (CRITICAL·LLM 불가 시)."""
    t = text.strip().lower()
    if t in _APPROVE_EXACT:
        return True
    return any(p in t for p in _APPROVE_SUBSTR)


def is_rule_reject(text: str) -> bool:
    t = text.strip().lower()
    if t in _REJECT_EXACT:
        return True
    return any(p in t for p in _REJECT_SUBSTR)


def classify_user_followup_rule(text: str) -> FollowupClassification:
    """LLM 없이 규칙만으로 분류."""
    if is_rule_reject(text):
        return FollowupClassification(FollowupDecision.REJECT, 1.0)
    if is_rule_approval(text):
        return FollowupClassification(FollowupDecision.APPROVE, 1.0)
    t = text.strip()
    if len(t) <= 24 and ("?" in t or "뭐" in t or "어떻" in t):
        return FollowupClassification(FollowupDecision.CLARIFY, 0.7)
    return FollowupClassification(FollowupDecision.UNRELATED, 0.5)


def _parse_decision(raw: object) -> FollowupDecision | None:
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    for d in FollowupDecision:
        if d.value == key:
            return d
    return None


def classify_user_followup(
    user_text: str,
    context_prompt: str,
    gemma: GemmaClient,
    *,
    use_llm: bool = True,
) -> FollowupClassification:
    """승인 대기 맥락에서 사용자 후속 발화 분류."""
    if not use_llm:
        return classify_user_followup_rule(user_text)

    ctx_line = (context_prompt or "").strip()[:400]
    user_block = f"확인 요청: {ctx_line}\n사용자 답: {user_text.strip()}"
    messages = [
        ChatMessage(role="system", content=APPROVAL_CLASSIFIER_SYSTEM),
        ChatMessage(role="user", content=user_block),
    ]
    raw_reply = gemma.chat(messages)
    if raw_reply.strip() == FALLBACK_KO or raw_reply.strip().startswith("로컬 언어 모델"):
        return classify_user_followup_rule(user_text)

    data = extract_json_object(raw_reply)
    if not data:
        return classify_user_followup_rule(user_text)

    decision = _parse_decision(data.get("decision"))
    if decision is None:
        return classify_user_followup_rule(user_text)

    conf_raw = data.get("confidence")
    try:
        confidence = float(conf_raw) if conf_raw is not None else 0.8
    except (TypeError, ValueError):
        confidence = 0.8
    confidence = max(0.0, min(1.0, confidence))
    return FollowupClassification(decision, confidence)


def resolve_followup_for_pending(
    user_text: str,
    context_prompt: str,
    gemma: GemmaClient,
    *,
    force_rule_only: bool,
    use_llm: bool,
) -> FollowupClassification:
    """critical·CRITICAL 도구는 규칙 승인만 허용 (LLM approve 무시)."""
    if force_rule_only:
        return classify_user_followup_rule(user_text)
    return classify_user_followup(user_text, context_prompt, gemma, use_llm=use_llm)
