"""미디어 재생·검색 완료 검증 — 기계 게이트(필수) + LLM verify(보조)."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from enum import Enum
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
- play에서 첨부 스크린샷이 있으면 **이미지가 정본**입니다. watch URL·플레이어·일시정지/재생 버튼·영상 프레임 등으로 판단하세요.
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

# Iris/Cursor 등 — 미디어 타깃이 아닌 활성 창
_NON_MEDIA_ACTIVE_SUBSTRINGS = (
    "iris",
    "cursor",
    "vscode",
    "visual studio code",
    "pycharm",
    "agent",
)

_PLATFORM_TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "youtube": ("youtube",),
    "netflix": ("netflix",),
    "spotify": ("spotify",),
    "browser": ("chrome", "edge", "firefox", "brave"),
    "unknown": ("chrome", "edge", "firefox", "youtube", "netflix", "spotify"),
}


class MediaCompletionPhase(str, Enum):
    """미디어 완료 판정 단계."""

    PRE_RANK = "pre_rank"
    SEARCH_DONE = "search_done"
    PLAY_DONE = "play_done"


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
def _active_window_from_blob(observation_blob: str) -> str:
    """observation blob에서 active_window 추출."""
    for chunk in re.findall(r"\{[^{}]*\"active_window\"[^{}]*\}", observation_blob):
        try:
            meta = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(meta, dict):
            aw = str(meta.get("active_window") or "").strip()
            if aw:
                return aw
    return ""


def _platform_target_visible(platform_hint: str, observation_blob: str) -> bool:
    """활성 창·요약에 플랫폼 미디어 창 신호가 있는지 (Iris/Cursor 단독이면 False)."""
    ph = (platform_hint or "unknown").strip().lower()
    hints = _PLATFORM_TITLE_HINTS.get(ph) or _PLATFORM_TITLE_HINTS["unknown"]
    active = _active_window_from_blob(observation_blob).lower()
    blob_l = observation_blob.lower()
    if active:
        if any(n in active for n in _NON_MEDIA_ACTIVE_SUBSTRINGS):
            if not any(h in active for h in hints):
                return False
        if any(h in active for h in hints):
            return True
    return any(h in blob_l for h in hints)


def _is_ide_only_active_window(observation_blob: str) -> bool:
    active = _active_window_from_blob(observation_blob).lower()
    if not active:
        return False
    if any(h in active for h in _PLATFORM_TITLE_HINTS["unknown"]):
        return False
    return any(n in active for n in _NON_MEDIA_ACTIVE_SUBSTRINGS)


def _search_url_only(blob: str, platform_hint: str) -> bool:
    """URL 검색 패턴만 있고 재생·결과 UI 신호는 없는지."""
    ph = (platform_hint or "unknown").strip().lower()
    pat = _SEARCH_URL_PATTERNS.get(ph) or _SEARCH_URL_PATTERNS["unknown"]
    if not pat.search(blob):
        return False
    play_pat = _PLAY_URL_PATTERNS.get(ph) or _PLAY_URL_PATTERNS["unknown"]
    if play_pat.search(blob):
        return False
    return not _has_result_list_ui_signal(blob)


def _has_result_list_ui_signal(observation_blob: str) -> bool:
    """UIA Hyperlink/ListItem 또는 결과 그리드형 summary."""
    for chunk in re.findall(r"\{[^{}]*\"elements\"\s*:\s*\[", observation_blob):
        start = chunk.find("{")
        depth = 0
        for i in range(start, min(start + 12000, len(observation_blob))):
            ch = observation_blob[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(observation_blob[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if not isinstance(obj, dict):
                        break
                    elements = obj.get("elements")
                    if not isinstance(elements, list):
                        break
                    links = 0
                    for el in elements:
                        if not isinstance(el, dict):
                            continue
                        ctype = str(el.get("type") or "").lower()
                        name = str(el.get("name") or "").strip()
                        if len(name) < 3:
                            continue
                        if "hyperlink" in ctype or "listitem" in ctype:
                            links += 1
                    if links >= 2:
                        return True
                    break
    text_no_url = re.sub(r"https?://\S+", "", observation_blob)
    if re.search(r"검색\s*결과|search\s*results", text_no_url, re.I):
        return True
    return False


def mechanical_search_achieved(
    platform_hint: str,
    observation_blob: str,
    search_query: str,
) -> bool:
    """검색 URL·쿼리 반영 (하위 호환·보조 신호). URL 단독 완료 판정에는 쓰지 않음."""
    ph = (platform_hint or "unknown").strip().lower()
    pat = _SEARCH_URL_PATTERNS.get(ph) or _SEARCH_URL_PATTERNS["unknown"]
    if pat.search(observation_blob):
        return True
    q = search_query.strip().lower()
    return bool(q) and q in observation_blob.lower()


def media_pre_rank_ready(
    platform: str,
    query: str,
    observation_blob: str,
    candidates: list[str],
) -> bool:
    """play rank 진입 — 필터 후보≥1·플랫폼 창. URL 단독·후보 0은 False."""
    if not candidates:
        return False
    if _is_ide_only_active_window(observation_blob):
        return False
    if not _platform_target_visible(platform, observation_blob):
        return False
    # 필터 통과 후보 ≥1 = 검색 결과 텍스트가 화면에 잡힌 것 (UIA hyperlink는 보조)
    return True


def media_search_complete(
    platform: str,
    query: str,
    observation_blob: str,
) -> bool:
    """search 종료 — 결과 UI·플랫폼 창. URL만으로는 False."""
    if _is_ide_only_active_window(observation_blob):
        return False
    if not _platform_target_visible(platform, observation_blob):
        return False
    if _has_result_list_ui_signal(observation_blob):
        return True
    q = query.strip().lower()
    if q and q in observation_blob.lower():
        if _search_url_only(observation_blob, platform):
            return False
        return True
    if mechanical_search_achieved(platform, observation_blob, query):
        if _search_url_only(observation_blob, platform):
            return False
        return _has_result_list_ui_signal(observation_blob)
    return False


def media_play_complete(platform: str, observation_blob: str) -> bool:
    """play 종료 — 재생 UI/URL. 검색 결과 URL만 열린 상태는 미완료."""
    ph = (platform or "unknown").strip().lower()
    search_pat = _SEARCH_URL_PATTERNS.get(ph) or _SEARCH_URL_PATTERNS["unknown"]
    play_pat = _PLAY_URL_PATTERNS.get(ph) or _PLAY_URL_PATTERNS["unknown"]
    has_search = bool(search_pat.search(observation_blob))
    has_play = bool(play_pat.search(observation_blob))
    if has_search and not has_play:
        return False
    return mechanical_play_achieved(platform, observation_blob)


def media_action_satisfied(
    action: str,
    platform: str,
    query: str,
    observation_blob: str,
    *,
    candidates: list[str] | None = None,
    phase: MediaCompletionPhase | str = MediaCompletionPhase.PRE_RANK,
) -> bool:
    """slots success_criteria와 동일 계약 — phase별 완료 판정."""
    act = (action or "").strip().lower()
    ph = phase.value if isinstance(phase, MediaCompletionPhase) else str(phase)
    if act == "search" and ph in {MediaCompletionPhase.SEARCH_DONE.value, "search_done"}:
        return media_search_complete(platform, query, observation_blob)
    if act == "play" and ph in {MediaCompletionPhase.PLAY_DONE.value, "play_done"}:
        return media_play_complete(platform, observation_blob)
    if act == "play" and ph in {MediaCompletionPhase.PRE_RANK.value, "pre_rank"}:
        return media_pre_rank_ready(
            platform, query, observation_blob, list(candidates or [])
        )
    return False
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
    screenshot_png: bytes | None = None,
) -> tuple[MediaVerifyResult | None, bool]:
    """LLM 보조 검증 — (결과, vision_used). play 시 스크린샷 1장 첨부 가능."""
    act = (media_action or "").strip().lower()
    shot_hint = ""
    if act == "play" and screenshot_png:
        shot_hint = (
            "첨부 스크린샷으로 watch URL·플레이어·재생/일시정지 UI를 확인하세요.\n"
        )
    user_body = (
        f"goal: {goal}\n"
        f"media_action: {media_action}\n"
        f"{shot_hint}"
        f"observation:\n{observation_blob[:2000]}\n"
    )
    images: tuple[bytes, ...] = ()
    if act == "play" and screenshot_png:
        images = (screenshot_png,)
    msgs = [
        ChatMessage("system", MEDIA_PLAYBACK_VERIFY_SYSTEM),
        ChatMessage("user", user_body, images=images),
    ]
    vision_used = False
    if images and hasattr(gemma, "chat_with_images"):
        raw, vision_used = gemma.chat_with_images(
            msgs,
            purpose=LlmPurpose.COMPUTER_USE,
            lane="computer_use",
        )
    else:
        raw = gemma.chat(
            msgs,
            purpose=LlmPurpose.COMPUTER_USE,
            lane="computer_use",
        )
    if _is_llm_unavailable(raw):
        return None, vision_used
    parsed = parse_media_verify_json(raw)
    return parsed, vision_used


def verify_media_with_llm_retries(
    gemma: GemmaClient,
    *,
    goal: str,
    media_action: str,
    observation_blob: str,
    screenshot_png: bytes | None = None,
    max_attempts: int = _MAX_LLM_VERIFY_ATTEMPTS,
) -> tuple[MediaVerifyResult | None, bool]:
    """LLM verify 최대 max_attempts회 — (마지막 결과, vision_used)."""
    last: MediaVerifyResult | None = None
    vision_used = False
    for _ in range(max(1, max_attempts)):
        result, used = llm_verify_media_playback(
            gemma,
            goal=goal,
            media_action=media_action,
            observation_blob=observation_blob,
            screenshot_png=screenshot_png,
        )
        vision_used = vision_used or used
        if result is None:
            return None, vision_used
        last = result
        if result.achieved:
            return result, vision_used
    return last, vision_used
def _is_llm_unavailable(text: str) -> bool:
    t = text.strip()
    return t == FALLBACK_KO or "로컬 언어 모델에 연결할 수 없습니다" in t
