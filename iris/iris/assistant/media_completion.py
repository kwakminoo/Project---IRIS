"""미디어 실행 완료 계약 — Router·MediaFlow 단일 진실 소스."""

from __future__ import annotations

from enum import Enum
from typing import Any

from iris.assistant.media_verify import (
    media_play_complete,
    media_pre_rank_ready,
    media_search_complete,
)

_PLATFORM_HINTS = frozenset({"youtube", "spotify", "netflix", "browser", "unknown"})
_MEDIA_ACTIONS = frozenset({"search", "play"})


class MediaSuccessCriteria(str, Enum):
    SEARCH_RESULTS_VISIBLE = "search_results_visible"
    PLAYBACK_CONFIRMED = "playback_confirmed"


class MediaExecutionPhase(str, Enum):
    PRE_RANK = "pre_rank"
    SEARCH_DONE = "search_done"
    PLAY_DONE = "play_done"


_CRITERIA_ALIASES: dict[str, MediaSuccessCriteria] = {
    "search_results_visible": MediaSuccessCriteria.SEARCH_RESULTS_VISIBLE,
    "playback_confirmed": MediaSuccessCriteria.PLAYBACK_CONFIRMED,
    "play_confirmed": MediaSuccessCriteria.PLAYBACK_CONFIRMED,
}


def parse_success_criteria(raw: object) -> MediaSuccessCriteria | None:
    """Router·slots 문자열 → enum (레거시 play_confirmed 포함)."""
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    if not key:
        return None
    return _CRITERIA_ALIASES.get(key)


def derive_success_criteria(
    media_action: str | None = None,
    task_type: str | None = None,
    *,
    slots: dict[str, Any] | None = None,
) -> MediaSuccessCriteria | None:
    """slots에 없으면 media_action·task_type에서 유도 — Router·실행 공용."""
    if slots:
        raw = slots.get("success_criteria") or slots.get("completion_signal")
        parsed = parse_success_criteria(raw)
        if parsed is not None:
            return parsed
        media_action = media_action or str(slots.get("media_action") or "")
        task_type = task_type or str(slots.get("task_type") or "")
    action = (media_action or "").strip().lower()
    if action == "play":
        return MediaSuccessCriteria.PLAYBACK_CONFIRMED
    if action == "search":
        return MediaSuccessCriteria.SEARCH_RESULTS_VISIBLE
    tt = (task_type or "").strip().lower()
    if tt == "media_play" and action in _MEDIA_ACTIONS:
        return derive_success_criteria(action, None)
    return None


def criteria_satisfied(
    criteria: MediaSuccessCriteria | str,
    phase: MediaExecutionPhase | str,
    *,
    platform: str,
    query: str,
    observation_blob: str,
    candidates: list[str] | None = None,
) -> bool:
    """
    단일 진실 소스. URL(search_query=) 단독으로 PLAYBACK_CONFIRMED / PRE_RANK True 금지.
    """
    crit = (
        criteria
        if isinstance(criteria, MediaSuccessCriteria)
        else parse_success_criteria(str(criteria))
    )
    if crit is None:
        return False
    ph = phase.value if isinstance(phase, MediaExecutionPhase) else str(phase).strip().lower()
    plat = (platform or "unknown").strip().lower()
    q = (query or "").strip()
    blob = observation_blob or ""
    cands = list(candidates or [])

    if ph == MediaExecutionPhase.PRE_RANK.value:
        if crit is not MediaSuccessCriteria.PLAYBACK_CONFIRMED:
            return False
        return media_pre_rank_ready(plat, q, blob, cands)

    if ph == MediaExecutionPhase.SEARCH_DONE.value:
        if crit is not MediaSuccessCriteria.SEARCH_RESULTS_VISIBLE:
            return False
        return media_search_complete(plat, q, blob)

    if ph == MediaExecutionPhase.PLAY_DONE.value:
        if crit is not MediaSuccessCriteria.PLAYBACK_CONFIRMED:
            return False
        return media_play_complete(plat, blob)

    return False


def normalize_routed_media_slots(slots: dict[str, Any]) -> dict[str, Any]:
    """LLM slots 정규화 + success_criteria·skill_id 유도 (unified·legacy 공용)."""
    out = dict(slots)

    ph_raw = out.get("platform_hint")
    if ph_raw is not None:
        ph = str(ph_raw).strip().lower()
        out["platform_hint"] = ph if ph in _PLATFORM_HINTS else "unknown"

    ma_raw = out.get("media_action")
    if ma_raw is not None:
        ma = str(ma_raw).strip().lower()
        if ma in _MEDIA_ACTIONS:
            out["media_action"] = ma
        else:
            out.pop("media_action", None)

    sq_raw = out.get("search_query")
    if isinstance(sq_raw, str):
        sq = sq_raw.strip()
        if sq:
            out["search_query"] = sq
        else:
            out.pop("search_query", None)

    parsed = parse_success_criteria(out.get("success_criteria"))
    if parsed is None:
        derived = derive_success_criteria(slots=out)
        if derived is not None:
            out["success_criteria"] = derived.value
    else:
        out["success_criteria"] = parsed.value

    action = str(out.get("media_action") or "").strip().lower()
    task_type = str(out.get("task_type") or "").strip().lower()
    sq = out.get("search_query")
    has_query = isinstance(sq, str) and bool(sq.strip())
    if action in _MEDIA_ACTIONS and has_query and (
        task_type == "media_play" or action in _MEDIA_ACTIONS
    ):
        out.setdefault("skill_id", "media_play")
        if task_type != "media_play":
            out.setdefault("task_type", "media_play")

    hint = out.get("last_execution_hint")
    if isinstance(hint, str) and hint.strip():
        out["last_execution_hint"] = hint.strip()[:80]
    elif "last_execution_hint" in out:
        out.pop("last_execution_hint", None)

    return out


def criteria_value_from_slots(slots: dict[str, Any]) -> str:
    """MediaPlaybackFlow·로그용 문자열."""
    c = derive_success_criteria(slots=slots)
    return c.value if c else ""


def set_last_execution_hint(assistant: Any, hint: str) -> None:
    """실패 시에만 — 다음 턴 Router user_block에 1줄."""
    text = hint.strip()[:80]
    if not text:
        return
    ctx = getattr(assistant, "ctx", None)
    if ctx is None:
        return
    ctx.slots["last_execution_hint"] = text


def clear_last_execution_hint(assistant: Any) -> None:
    ctx = getattr(assistant, "ctx", None)
    if ctx is None:
        return
    ctx.slots.pop("last_execution_hint", None)
