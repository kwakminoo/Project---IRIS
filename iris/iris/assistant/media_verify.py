"""미디어 재생·검색 완료 검증 — 기계 게이트(필수) + LLM verify(보조)."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence
from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.ai.response_parser import extract_json_object
from iris.ai.thinking_policy import LlmPurpose
if TYPE_CHECKING:
    from iris.ai.gemma_client import GemmaClient
# 재생 확인 — URL/UIA 힌트, LLM은 보조
MEDIA_PLAYBACK_VERIFY_SYSTEM = """당신은 Iris Media Playback Verifier입니다.
goal, media_action, 화면 observation 요약을 보고 목표 달성 여부를 판단하세요.
규칙:
- media_action=search: 검색 결과 페이지·쿼리 반영 여부.
- media_action=play: 실제 재생/시청 UI 신호(예: youtube watch/shorts, spotify track+재생, netflix watch).
- play에서 재생 신호가 없으면 achieved=false (step_complete와 동일한 엄격함).
- JSON만 출력: {"achieved": true|false, "evidence": "한국어", "missing": "한국어 또는 빈 문자열"}
"""
_SEARCH_URL_PATTERNS: dict[str, re.Pattern[str]] = {
    "youtube": re.compile(r"search_query=|youtube\.com/results", re.I),
    "spotify": re.compile(r"open\.spotify\.com/search|spotify\.com/search", re.I),
    "netflix": re.compile(r"netflix\.com/search", re.I),
    "browser": re.compile(r"google\.com/search\?q=", re.I),
    "unknown": re.compile(r"google\.com/search\?q=", re.I),
}
_PLAY_URL_PATTERNS: dict[str, re.Pattern[str]] = {
    "youtube": re.compile(r"youtube\.com/watch|/shorts/", re.I),
    "spotify": re.compile(
        r"open\.spotify\.com/(track|album|episode)|spotify:track", re.I
    ),
    "netflix": re.compile(r"netflix\.com/watch|/watch/|netflix\.com/.*/player", re.I),
    "browser": re.compile(
        r"youtube\.com/watch|/shorts/|open\.spotify\.com/(track|album)", re.I
    ),
    "unknown": re.compile(
        r"youtube\.com/watch|/shorts/|open\.spotify\.com/track|netflix\.com/watch",
        re.I,
    ),
}
# Spotify: URL + 재생 UI 힌트(OCR/UIA 최소 집합)
_SPOTIFY_PLAYING_UI = re.compile(
    r"(playing|now playing|재생\s*중|일시정지|pause|spotify\.com)",
    re.I,
)
_MEDIA_VERIFY_OK_PREFIX = "media_verify_ok:"
_MAX_LLM_VERIFY_ATTEMPTS = 3
_MAX_MECHANICAL_PERCEIVE_RETRY = 2
@dataclass(frozen=True)
class MediaVerifyResult:
    achieved: bool
    evidence: str
    missing: str
def parse_media_verify_json(raw: str) -> MediaVerifyResult | None:
    data = extract_json_object(raw)
    if not data:
        return None
    achieved = bool(data.get("achieved"))
    evidence = str(data.get("evidence") or "").strip()
    missing = str(data.get("missing") or "").strip()
    return MediaVerifyResult(achieved=achieved, evidence=evidence, missing=missing)
def mechanical_search_achieved(
    platform_hint: str,
    observation_blob: str,
    search_query: str,
) -> bool:
    """검색 결과 URL·쿼리 반영 1차 게이트."""
    ph = (platform_hint or "unknown").strip().lower()
    pat = _SEARCH_URL_PATTERNS.get(ph) or _SEARCH_URL_PATTERNS["unknown"]
    if pat.search(observation_blob):
        return True
    q = search_query.strip().lower()
    return bool(q) and q in observation_blob.lower()
def mechanical_play_achieved(platform_hint: str, observation_blob: str) -> bool:
    """재생/시청 페이지·UI 신호 1차 게이트 — LLM verify 전 필수."""
    ph = (platform_hint or "unknown").strip().lower()
    blob = observation_blob
    url_pat = _PLAY_URL_PATTERNS.get(ph) or _PLAY_URL_PATTERNS["unknown"]
    if url_pat.search(blob):
        if ph == "spotify":
            return bool(_SPOTIFY_PLAYING_UI.search(blob))
        return True
    if ph == "spotify" and "spotify.com" in blob.lower():
        return bool(_SPOTIFY_PLAYING_UI.search(blob))
    return False
def has_media_verify_ok_marker(observations: Sequence[str]) -> bool:
    """Media Flow 또는 이전 검증이 남긴 media_verify_ok 관측."""
    for obs in observations:
        if obs.strip().startswith(_MEDIA_VERIFY_OK_PREFIX):
            return True
    return False
def format_media_verify_ok(media_action: str, evidence: str = "") -> str:
    """observation에 기록 — CU step_complete 가드 통과용."""
    ev = evidence.strip()[:120]
    if ev:
        return f"{_MEDIA_VERIFY_OK_PREFIX} {media_action} | {ev}"
    return f"{_MEDIA_VERIFY_OK_PREFIX} {media_action}"
def observation_blob_from(observations: Sequence[str], *, tail: int = 12) -> str:
    return "\n".join(observations[-tail:])
def play_step_complete_allowed(
    slots: dict[str, object],
    observations: Sequence[str],
) -> tuple[bool, str]:
    """
    CU step_complete — media_action=play 시 기계 게이트 또는 media_verify_ok 필요.
    반환: (허용 여부, 거부 시 observation에 넣을 메시지)
    """
    action = str(slots.get("media_action") or "").strip().lower()
    if action != "play":
        return True, ""
    if has_media_verify_ok_marker(observations):
        return True, ""
    platform = str(slots.get("platform_hint") or slots.get("app_hint") or "unknown")
    blob = observation_blob_from(observations)
    if mechanical_play_achieved(platform, blob):
        return True, ""
    return (
        False,
        "verify_required: play not confirmed (재생/시청 URL·UI 신호 없음)",
    )
def llm_verify_media_playback(
    gemma: GemmaClient,
    *,
    goal: str,
    media_action: str,
    observation_blob: str,
) -> MediaVerifyResult | None:
    """LLM 보조 검증 — 기계 게이트 실패 후에만 호출."""
    user_body = (
        f"goal: {goal}\n"
        f"media_action: {media_action}\n"
        f"observation:\n{observation_blob[:2000]}\n"
    )
    raw = gemma.chat(
        [
            ChatMessage("system", MEDIA_PLAYBACK_VERIFY_SYSTEM),
            ChatMessage("user", user_body),
        ],
        purpose=LlmPurpose.COMPUTER_USE,
        lane="computer_use",
    )
    if _is_llm_unavailable(raw):
        return None
    return parse_media_verify_json(raw)
def verify_media_with_llm_retries(
    gemma: GemmaClient,
    *,
    goal: str,
    media_action: str,
    observation_blob: str,
    max_attempts: int = _MAX_LLM_VERIFY_ATTEMPTS,
) -> MediaVerifyResult | None:
    """LLM verify 최대 max_attempts회 — 무한 루프 방지."""
    last: MediaVerifyResult | None = None
    for _ in range(max(1, max_attempts)):
        result = llm_verify_media_playback(
            gemma,
            goal=goal,
            media_action=media_action,
            observation_blob=observation_blob,
        )
        if result is None:
            return None
        last = result
        if result.achieved:
            return result
    return last
def _is_llm_unavailable(text: str) -> bool:
    t = text.strip()
    return t == FALLBACK_KO or "로컬 언어 모델에 연결할 수 없습니다" in t
