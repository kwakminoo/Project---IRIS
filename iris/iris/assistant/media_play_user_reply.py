"""미디어 플로우 결과 기반 사용자 멘트 — 로컬 LLM 합성 + 결정적 폴백."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from iris.ai.gemma_client import FALLBACK_KO
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.computer_use_agent import USER_QUESTION_PREFIX

if TYPE_CHECKING:
    from iris.ai.gemma_client import GemmaClient

# Gemini/Gemma 사용자 멘트 — 마크다운·JSON 출력 금지
_MEDIA_USER_REPLY_SYSTEM = """당신은 Iris(Windows 로컬 비서)가 사용자에게 보여 줄 한국어 안내 문장만 작성합니다.

입력으로 JSON 하나가 옵니다. flow·platform·action·query·outcome_code·metrics·log_tags 필드를 참고합니다.

작성 규칙:
- 플레인 텍스트만. 마크다운·코드블록·JSON·목록 번호 과용 금지.
- 과장하거나 거짓으로 "반드시 해결"처럼 단정하지 말 것.
- 원인 요약은 짧게(한 문장 이내), 다음 행동은 구체적으로 1~3문장.
- 성공(success_*) 멘트는 간단히 재생 또는 검색이 진행되었음을 알림.
- outcome이 확장 프로그램·브라우저·네트워크와 관련이면 Chrome Iris 확장(YouTube 사이트 허용, 몇 초 뒤 재요청 등)을 자연스럽게 안내 가능.
- DOM/UIA 같은 내부 용어는 쓰지 말 것.
- 불필요한 이모지 금지.
"""

_MAX_PAYLOAD_CHARS = 1800
_MAX_REPLY_CHARS = 900

# 사용자 확인이 필요했던 멘트 — orchestrator·USER_QUESTION 접두 규칙 유지
_OUTCOMES_WITH_USER_QUESTION_PREFIX: frozenset[str] = frozenset(
    {
        "query_missing",
        "search_query_needed",
        "legacy_gate_no_candidates",
        "legacy_rank_ask_user",
        "youtube_dom_skipped_no_monitor",
        "youtube_dom_empty_after_poll",
        "youtube_dom_parse_empty",
        "youtube_dom_pick_fail",
    }
)


class MediaPlayOutcome(StrEnum):
    """미디어 실행기가 분류하는 사용자 멘트용 결과 코드."""

    QUERY_MISSING = "query_missing"
    SEARCH_QUERY_NEEDED = "search_query_needed"
    OPEN_URL_FAIL = "open_url_fail"
    SUCCESS_SEARCH_OPEN = "success_search_open"
    SEARCH_VERIFY_FAIL = "search_verify_fail"

    SUCCESS_PLAY_DOM = "success_play_dom"
    SUCCESS_PLAY_DOM_LLM = "success_play_dom_llm"
    SUCCESS_PLAY_LEGACY = "success_play_legacy"
    SUCCESS_PLAY_LEGACY_LLM = "success_play_legacy_llm"

    YOUTUBE_DOM_SKIPPED_NO_MONITOR = "youtube_dom_skipped_no_monitor"
    YOUTUBE_DOM_EMPTY_AFTER_POLL = "youtube_dom_empty_after_poll"
    YOUTUBE_DOM_PARSE_EMPTY = "youtube_dom_parse_empty"
    YOUTUBE_DOM_PICK_FAIL = "youtube_dom_pick_fail"
    YOUTUBE_DOM_OPEN_WATCH_FAIL = "youtube_dom_open_watch_fail"
    YOUTUBE_DOM_VERIFY_FAIL_PLAY = "youtube_dom_verify_fail_play"

    LEGACY_GATE_NO_CANDIDATES = "legacy_gate_no_candidates"
    LEGACY_RANK_ASK_USER = "legacy_rank_ask_user"
    LEGACY_CLICK_FAIL = "legacy_click_fail"
    LEGACY_VERIFY_FAIL_PLAY = "legacy_verify_fail_play"


def _fallback_body(code: MediaPlayOutcome, query: str) -> str:
    """로컬 LLM 불가 또는 합성 실패 시 고정 폴백."""
    q = (query or "").strip()
    qi = q[:48] + ("…" if len(q) > 48 else "")
    fb: dict[str, str] = {
        MediaPlayOutcome.QUERY_MISSING: "어떤 곡이나 영상을 찾거나 재생하면 될까요?",
        MediaPlayOutcome.SEARCH_QUERY_NEEDED: "검색어를 한 번 더 알려 주세요.",
        MediaPlayOutcome.OPEN_URL_FAIL: "미디어 페이지를 열지 못했습니다. 브라우저 상태를 확인한 뒤 다시 요청해 주세요.",
        MediaPlayOutcome.SUCCESS_SEARCH_OPEN: f"'{qi}' 검색 결과 페이지를 열었습니다.",
        MediaPlayOutcome.SEARCH_VERIFY_FAIL: "검색 페이지는 열렸는데 결과 화면을 확인하지 못했습니다. 잠깐 후 다시 요청하거나 화면을 확인해 주세요.",
        MediaPlayOutcome.SUCCESS_PLAY_DOM: f"'{qi}' 재생을 시작했습니다.",
        MediaPlayOutcome.SUCCESS_PLAY_DOM_LLM: f"'{qi}' 재생을 시작했습니다.",
        MediaPlayOutcome.SUCCESS_PLAY_LEGACY: f"'{qi}' 재생을 시작했습니다.",
        MediaPlayOutcome.SUCCESS_PLAY_LEGACY_LLM: f"'{qi}' 재생을 시작했습니다.",
        MediaPlayOutcome.YOUTUBE_DOM_SKIPPED_NO_MONITOR: "유튜브 결과를 프로그램이 읽지 못했습니다. Iris에서 Chrome 확장 연결 상태를 확인해 주세요.",
        MediaPlayOutcome.YOUTUBE_DOM_EMPTY_AFTER_POLL: "유튜브 검색 결과를 아직 받지 못했습니다. Chrome에서 Iris 확장에 YouTube가 허용돼 있는지 확인하고, 결과가 로드된 뒤 몇 초 뒤 다시 요청해 주세요.",
        MediaPlayOutcome.YOUTUBE_DOM_PARSE_EMPTY: "유튜브 검색 결과 링크를 해석하지 못했습니다. 잠시 후 다시 요청하거나 재생할 영상 제목을 더 구체적으로 알려 주세요.",
        MediaPlayOutcome.YOUTUBE_DOM_PICK_FAIL: "검색 결과에서 재생할 영상을 고르지 못했습니다. 제목을 조금 더 구체적으로 알려 주세요.",
        MediaPlayOutcome.YOUTUBE_DOM_OPEN_WATCH_FAIL: "선택한 영상 페이지를 열지 못했습니다. 다시 요청해 주세요.",
        MediaPlayOutcome.YOUTUBE_DOM_VERIFY_FAIL_PLAY: "재생이 시작된 것 같은지 확인하지 못했습니다. 브라우저 재생 상태를 확인하거나 다시 요청해 주세요.",
        MediaPlayOutcome.LEGACY_GATE_NO_CANDIDATES: "검색 결과 제목을 화면에서 읽지 못했습니다. 몇 초 뒤 다시 요청하거나 재생할 영상 제목을 알려 주세요.",
        MediaPlayOutcome.LEGACY_RANK_ASK_USER: "어떤 영상을 눌러야 할지 확신하지 못했습니다. 조금 더 구체적인 제목으로 다시 요청해 주세요.",
        MediaPlayOutcome.LEGACY_CLICK_FAIL: "화면에서 항목을 눌러 열지 못했습니다. 직접 선택하거나 다시 요청해 주세요.",
        MediaPlayOutcome.LEGACY_VERIFY_FAIL_PLAY: "재생 화면을 확인하지 못했습니다. 브라우저에서 상태를 확인하거나 다시 요청해 주세요.",
    }
    return fb.get(code, "요청을 마치지 못했습니다. 잠시 후 다시 시도해 주세요.")


def build_media_reply_payload(
    *,
    goal: str,
    query: str,
    platform: str,
    action: str,
    outcome: MediaPlayOutcome,
    tier_path: list[str],
    metrics: dict[str, Any],
    log_tags: list[str],
) -> dict[str, Any]:
    """LLM 사용자 멘트용 안전 요약 페이로드(원문 관측·URL 제외)."""
    return {
        "flow": "media_play",
        "platform": (platform or "unknown").strip().lower(),
        "action": (action or "").strip().lower(),
        "query": (query or "")[:120],
        "goal": (goal or "")[:200],
        "outcome_code": outcome.value,
        "tier_path": tier_path[:8],
        "metrics": metrics,
        "log_tags": [t[:80] for t in (log_tags or [])[:12]],
    }


def _strip_markdownish(text: str) -> str:
    t = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    t = re.sub(r"```[\s\S]*?```", "", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    return t.strip()


def synthesize_media_user_reply(
    gemma: "GemmaClient",
    *,
    payload: dict[str, Any],
) -> str:
    """
    로컬 LLM으로 한국어 멘트 생성. 실패·빈 응답 시 빈 문자열.
    """
    from iris.ai.gemma_client import ChatMessage

    raw_json = json.dumps(payload, ensure_ascii=False)
    if len(raw_json) > _MAX_PAYLOAD_CHARS:
        raw_json = raw_json[: _MAX_PAYLOAD_CHARS - 3] + "..."
    user_msg = f"아래 JSON을 참고해 Iris가 사용자에게 보낼 최종 한국어 문장만 작성하세요.\n{raw_json}"
    try:
        out = gemma.chat(
            [
                ChatMessage("system", _MEDIA_USER_REPLY_SYSTEM),
                ChatMessage("user", user_msg),
            ],
            purpose=LlmPurpose.MEDIA_USER_REPLY,
            lane=None,
        )
    except Exception:
        return ""
    t = out.strip()
    if not t or t == FALLBACK_KO or "로컬 언어 모델에 연결할 수 없습니다" in t:
        return ""
    t = _strip_markdownish(t)
    if len(t) > _MAX_REPLY_CHARS:
        t = t[: _MAX_REPLY_CHARS - 1] + "…"
    return t


def finalize_media_user_message(
    outcome: MediaPlayOutcome,
    synthesized: str,
    *,
    query: str,
) -> str:
    """폴백 문구·USER_QUESTION 접두 규칙 적용 후 최종 사용자 문자열."""
    body = (synthesized or "").strip()
    if not body:
        body = _fallback_body(outcome, query)

    oc = outcome.value
    needs_prefix = oc in _OUTCOMES_WITH_USER_QUESTION_PREFIX
    if needs_prefix and not body.startswith(USER_QUESTION_PREFIX):
        return f"{USER_QUESTION_PREFIX} {body}"
    return body


def media_reply_from_context(
    gemma: Any,
    *,
    goal: str,
    query: str,
    platform: str,
    action: str,
    outcome: MediaPlayOutcome,
    tier_path: list[str],
    metrics: dict[str, Any] | None = None,
    log_tags: list[str] | None = None,
) -> str:
    """페이로드 생성 → 합성 → finalize 한 번에."""
    payload = build_media_reply_payload(
        goal=goal,
        query=query,
        platform=platform,
        action=action,
        outcome=outcome,
        tier_path=tier_path,
        metrics=dict(metrics or {}),
        log_tags=list(log_tags or []),
    )
    synth = ""
    if hasattr(gemma, "chat"):
        synth = synthesize_media_user_reply(gemma, payload=payload)
    return finalize_media_user_message(outcome, synth, query=query)
