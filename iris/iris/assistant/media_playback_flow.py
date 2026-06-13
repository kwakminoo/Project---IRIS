"""미디어 검색·재생 고정 단계 플로우 — 의도·선택·완료 판단은 LLM, URL·검증 게이트는 코드."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.ai.response_parser import extract_json_object
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.media_completion import (
    MediaExecutionPhase,
    MediaSuccessCriteria,
    clear_last_execution_hint,
    criteria_satisfied,
    criteria_value_from_slots,
    derive_success_criteria as resolve_media_contract,
    set_last_execution_hint,
)
from iris.assistant.media_play_user_reply import MediaPlayOutcome, media_reply_from_context
from iris.assistant.media_verify import (
    _MAX_MECHANICAL_PERCEIVE_RETRY,
    format_media_verify_ok,
    mechanical_play_achieved,
    mechanical_search_achieved,
    verify_media_with_llm_retries,
)
from iris.automation import uia_reader, window_controller
from iris.automation.window_controller import WindowInfo
from iris.automation.media_urls import build_media_open_url
from iris.automation.tool_types import AutomationToolResult
from iris.automation.youtube_dom import (
    YoutubeWatchCandidate,
    extract_video_id,
    parse_youtube_search_results,
    pick_watch_url,
)
from iris.config.settings import Settings
from iris.core.activity_sink import push_activity_line
from iris.monitoring import ocr_engine, screen_capture
from iris.monitoring.sync_wait import wait_until

if TYPE_CHECKING:
    from iris.assistant.computer_use_agent import ComputerUseAgent

# play 경로: 의도적 sleep 없음 — perceive 재시도만으로 로딩 흡수
_PLAY_CANDIDATE_MAX = 5
_RANKER_AUTO_PLAY_MIN_CONFIDENCE = 0.45
_PERCEIVE_LOAD_MAX_RETRIES = 3
# YouTube DOM — 확장 ingest 이벤트·조건 대기(고정 sleep 폴링 없음)
_YOUTUBE_DOM_WAIT_TIMEOUT_SEC = 8.0
_ADDRBAR_FOCUS_WAIT_SEC = 0.2
_CANDIDATE_NAME_MAX_LEN = 240
_PERCEIVE_DETAIL_MAX = 3500
_PERCEIVE_MESSAGE_MAX = 1600
_CANDIDATE_MIN_TOKEN_OVERLAP = 0.2
_BROWSER_TITLE_SUBS = ("Chrome", "Microsoft Edge", "Edge", "Firefox")

MEDIA_RESULT_RANKER_SYSTEM = """당신은 Iris Media Result Ranker입니다.
첨부 스크린샷이 **정본**입니다. candidates는 보조 힌트(0번=맨 위)입니다.
규칙:
- 스크린샷에서 검색 결과 영상 제목을 확인하고, 클릭할 항목을 고르세요.
- pick_name: uia_click에 쓸 문자열. **가능하면 candidates[pick_index]와 완전히 동일**하게.
- pick_name이 candidates에 없으면 스크린샷에서 읽은 제목을 넣되, 불확실하면 pick_index=0·pick_name=candidates[0]을 우선하세요.
- STT 오타(예: 알레프 칫챗 ↔ Aleph, Chit Chat)를 허용합니다. 관련 영상이 보이면 pick을 null로 두지 마세요.
- 사용자에게 고르게 하지 마세요. 가장 유력한 항목을 스스로 선택합니다.
- pick_index: candidates의 0-based 인덱스. 반드시 후보 범위 안의 정수.
- 제목이 검색어와 조금 다르도(띄어쓰기·부제·가수명) 의미상 같으면 선택하세요.
- Shorts·커버·라이브 중 원곡·공식 뮤직비디오가 더 맞으면 그쪽을 우선하세요.
- 후보가 전혀 무관하고 스크린샷에도 해당 영상이 없을 때만 pick_index·pick_name을 null.
- JSON만 출력: {"pick_index": 0, "pick_name": "문자열 또는 null", "confidence": 0.0~1.0, "reason": "한국어"}
"""

_RANK_LOG_JSON_MAX = 800
_VIDEO_TITLE_MIN_LEN = 8
_VIDEO_TITLE_MAX_LEN = 240

# YouTube 제목 필터 — UI·메타 라벨 제외 (테스트로 고정)
_VIDEO_TITLE_JUNK_SUBSTRINGS = (
    "조회수",
    "구독",
    "만회",
    "천회",
    "전에",
    "시청",
    "mix ·",
    "mix·",
    "재생 목록",
    "playlist",
)
_VIDEO_TITLE_JUNK_EXACT = frozenset(
    {
        "home",
        "search",
        "filter",
        "filters",
        "로그인",
        "premium",
        "youtube",
        "홈",
        "검색",
        "탐색",
    }
)
_SYMBOLS_ONLY_RE = re.compile(r"^[\d\s\W_]+$", re.UNICODE)

@dataclass(frozen=True)
class MediaTarget:
    """플랫폼별 perceive·클릭 대상 창."""

    window_title_sub: str
    focus_before_perceive: bool = True
    url_domain_hint: str | None = None
    alt_title_subs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedMediaWindow:
    """open_url 직후 화면 기준으로 고른 미디어 창."""

    hwnd: int
    title_sub: str
    match_reason: str


_IDE_TITLE_PENALTY = ("iris", "cursor", "vscode", "visual studio", "pycharm", "agent")


def resolve_media_target(platform_hint: str) -> MediaTarget:
    """platform_hint → 타깃 창·URL 검증 힌트."""
    ph = (platform_hint or "unknown").strip().lower()
    if ph == "youtube":
        return MediaTarget("YouTube", url_domain_hint="youtube.com")
    if ph == "netflix":
        return MediaTarget("Netflix", url_domain_hint="netflix.com")
    if ph == "spotify":
        return MediaTarget("Spotify", url_domain_hint="open.spotify.com")
    if ph in {"browser", "unknown"}:
        return MediaTarget(
            _BROWSER_TITLE_SUBS[0],
            url_domain_hint=None,
            alt_title_subs=_BROWSER_TITLE_SUBS,
        )
    return MediaTarget(ph.capitalize() or "Chrome", alt_title_subs=_BROWSER_TITLE_SUBS)

# 검색 결과가 아닌 UI 라벨(후보 제외)
_UI_JUNK_SUBSTRINGS = (
    "home",
    "search",
    "sign in",
    "로그인",
    "구독",
    "subscribe",
    "skip",
    "menu",
    "settings",
    "설정",
    "filter",
    "filters",
    "sort by",
    "정렬",
    "youtube premium",
    "premium",
    "guide",
    "library",
    "history",
    "탐색",
    "홈",
    "검색",
    "재생",
    "pause",
    "play ",
    "chrome",
    "edge",
    "firefox",
    "minimize",
    "maximize",
    "close",
)

_SKIP_LINE_PREFIXES = (
    "perceive:",
    "windows:",
    "tool_",
    "goal:",
    "slots:",
    "recipe_hint:",
    "media_verify_ok:",
    "verify_required:",
)

# 후보 필터 — 광고·Shorts·시스템/UI 잡음
_MEDIA_JUNK_SUBSTRINGS = (
    "sponsored",
    "광고",
    " shorts",
    "#shorts",
    "/shorts/",
    "cursor",
    "agent",
    "iris",
    "화면 캡처",
    "[monitor_target",
    "브라우저",
    "perceive:",
    "windows:",
)


def _query_tokens(query: str) -> list[str]:
    """검색어에서 2글자 이상 토큰 (중복 제거, 순서 유지)."""
    raw = re.findall(r"[\w가-힣]{2,}", query.strip().lower())
    seen: set[str] = set()
    out: list[str] = []
    for t in raw:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def token_overlap_score(text: str, query_tokens: list[str]) -> float:
    """후보 제목과 검색어 토큰 겹침 비율 (0~1)."""
    if not query_tokens:
        return 1.0
    text_tokens = set(re.findall(r"[\w가-힣]+", text.lower()))
    if not text_tokens:
        return 0.0
    hits = sum(
        1
        for t in query_tokens
        if t in text_tokens or any(t in wt or wt in t for wt in text_tokens)
    )
    return hits / len(query_tokens)


def filter_media_candidates(
    candidates: list[str],
    *,
    platform: str,
    search_query: str,
    exclude_shorts: bool = True,
    exclude_ads: bool = True,
    require_query_token_overlap: bool = True,
) -> list[str]:
    """광고·Shorts·시스템 라벨 제거. play pre-rank는 토큰 겹침 비활성 가능."""
    del platform  # 플랫폼별 규칙 확장 슬롯
    tokens = _query_tokens(search_query) if require_query_token_overlap else []
    out: list[str] = []
    for name in candidates:
        low = name.lower()
        if exclude_shorts and (
            "shorts" in low or "#shorts" in low or "/shorts/" in low
        ):
            continue
        if exclude_ads and (
            "sponsored" in low
            or "광고" in name
            or re.search(r"\bad\b", low)
        ):
            continue
        if any(j in low for j in _MEDIA_JUNK_SUBSTRINGS):
            continue
        if any(j in low for j in _UI_JUNK_SUBSTRINGS) and len(name.strip()) < 28:
            continue
        if tokens and token_overlap_score(name, tokens) < _CANDIDATE_MIN_TOKEN_OVERLAP:
            continue
        out.append(name)
    return out


def _is_video_title_shape(name: str) -> bool:
    """영상 제목 형태인지 (길이·URL·숫자만·UI 라벨)."""
    t = name.strip()
    if len(t) < _VIDEO_TITLE_MIN_LEN or len(t) > _VIDEO_TITLE_MAX_LEN:
        return False
    if re.match(r"^https?://", t, re.I):
        return False
    if t.startswith("{") or t.startswith("["):
        return False
    if "perception_source" in t or '"elements"' in t:
        return False
    if _SYMBOLS_ONLY_RE.match(t):
        return False
    low = t.lower()
    if low in _VIDEO_TITLE_JUNK_EXACT:
        return False
    if any(j in low for j in _VIDEO_TITLE_JUNK_SUBSTRINGS):
        return False
    if any(j in low for j in _UI_JUNK_SUBSTRINGS) and len(t) < 28:
        return False
    if low in {"mix", "playlist", "재생목록"}:
        return False
    return True


def filter_video_title_candidates(
    candidates: list[str],
    *,
    platform: str,
    search_query: str,
) -> list[str]:
    """filter_media_candidates 이후 — 영상 제목만 Ranker에 전달."""
    del platform
    kept = [c for c in candidates if _is_video_title_shape(c)]
    tokens = _query_tokens(search_query)
    if not tokens or len(kept) <= 1:
        return kept[:_PLAY_CANDIDATE_MAX]
    # 검색어 토큰 겹침 높은 순 정렬 (겹침 없어도 제목형이면 유지)
    kept.sort(key=lambda c: (-token_overlap_score(c, tokens), c))
    return kept[:_PLAY_CANDIDATE_MAX]


def mechanical_pick_candidate(
    candidates: list[str],
    search_query: str,
) -> str | None:
    """Ranker null 시 토큰 겹침 최고 후보; 동점·0점이면 candidates[0]."""
    if not candidates:
        return None
    tokens = _query_tokens(search_query)
    if not tokens:
        return candidates[0]
    best_name = candidates[0]
    best_score = -1.0
    for c in candidates:
        score = token_overlap_score(c, tokens)
        if score > best_score:
            best_score = score
            best_name = c
    return best_name


def _patch_perception_active_window(detail: str, active_window: str) -> str:
    """resolved 창 제목으로 perception detail의 active_window 정규화."""
    if not detail or not active_window:
        return detail
    try:
        meta = json.loads(detail)
    except json.JSONDecodeError:
        return detail
    if not isinstance(meta, dict):
        return detail
    meta["active_window"] = active_window
    return json.dumps(meta, ensure_ascii=False)


def candidates_ready_for_rank(
    platform: str,
    query: str,
    observation_blob: str,
    candidates: list[str],
    *,
    criteria: MediaSuccessCriteria | str | None = None,
) -> bool:
    """Ranker 진입 전 — criteria_satisfied(PRE_RANK) thin wrapper."""
    crit = criteria or MediaSuccessCriteria.PLAYBACK_CONFIRMED
    return criteria_satisfied(
        crit,
        MediaExecutionPhase.PRE_RANK,
        platform=platform,
        query=query,
        observation_blob=observation_blob,
        candidates=candidates,
    )


def derive_success_criteria(slots: dict[str, Any]) -> str:
    """Router slots → 완료 계약 문자열 (테스트·로그 호환)."""
    return criteria_value_from_slots(slots)


def resolve_focus_window_after_open(
    platform: str,
    *,
    open_url: str,
    window_list_blob: str,
    last_perception_active: str = "",
) -> ResolvedMediaWindow | None:
    """open_url 직후 창 목록·perception으로 이번에 연 미디어 창 선택."""
    target = resolve_media_target(platform)
    host = ""
    try:
        host = (urlparse(open_url).netloc or "").lower().replace("www.", "")
    except ValueError:
        host = ""
    active = (last_perception_active or window_controller.get_active_window_title()).strip()
    wins = window_controller.list_visible_windows()
    if not wins and window_list_blob:
        for line in window_list_blob.splitlines():
            title = line.strip()
            if len(title) < 3:
                continue
            wins.append(WindowInfo(title, 0, 0, 800, 600, 0))
    scored: list[tuple[float, Any, str]] = []
    for w in wins:
        title = getattr(w, "title", str(w))
        hwnd = int(getattr(w, "hwnd", 0) or 0)
        title_l = title.lower()
        score = 0.0
        reasons: list[str] = []
        if target.window_title_sub.lower() in title_l:
            score += 40.0
            reasons.append("platform_in_title")
        for alt in target.alt_title_subs:
            if alt.lower() in title_l:
                score += 28.0
                reasons.append("browser_in_title")
                break
        if target.url_domain_hint and target.url_domain_hint.lower() in title_l:
            score += 25.0
            reasons.append("domain_in_title")
        if host and host in title_l:
            score += 22.0
            reasons.append("url_host_in_title")
        if active and active.lower() in title_l or title_l in active.lower():
            score += 15.0
            reasons.append("active_match")
        if any(p in title_l for p in _IDE_TITLE_PENALTY):
            score -= 55.0
            reasons.append("ide_penalty")
        if score > 0:
            scored.append((score, (hwnd, title), ",".join(reasons)))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best_score, (hwnd, title), reason = scored[0]
    if best_score <= 0:
        return None
    title_sub = target.window_title_sub
    if target.window_title_sub.lower() not in title.lower():
        for alt in target.alt_title_subs:
            if alt.lower() in title.lower():
                title_sub = alt
                break
        else:
            title_sub = title[:48]
    return ResolvedMediaWindow(hwnd=hwnd, title_sub=title_sub, match_reason=reason)


def should_run_media_flow(slots: dict[str, Any] | None) -> bool:
    """Router skill_id 또는 media_action+search_query로 Media Flow 진입."""
    if not slots:
        return False
    if str(slots.get("skill_id") or "").strip() == "media_play":
        query = slots.get("search_query")
        return isinstance(query, str) and bool(query.strip())
    action = str(slots.get("media_action") or "").strip().lower()
    query = slots.get("search_query")
    return action in {"search", "play"} and isinstance(query, str) and bool(query.strip())


@dataclass(frozen=True)
class MediaRankerResult:
    pick_name: str | None
    pick_index: int | None
    confidence: float
    reason: str


def parse_media_ranker_json(raw: str) -> MediaRankerResult | None:
    data = extract_json_object(raw)
    if not data:
        return None
    pick_raw = data.get("pick_name")
    pick = pick_raw.strip() if isinstance(pick_raw, str) and pick_raw.strip() else None
    pick_index: int | None = None
    idx_raw = data.get("pick_index")
    if idx_raw is not None:
        try:
            pick_index = int(idx_raw)
        except (TypeError, ValueError):
            pick_index = None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(data.get("reason") or "").strip()
    return MediaRankerResult(
        pick_name=pick, pick_index=pick_index, confidence=conf, reason=reason
    )


def _is_usable_candidate_name(name: str) -> bool:
    """검색 결과 제목으로 쓸 만한 문자열인지."""
    t = name.strip()
    if len(t) < 3:
        return False
    if len(t) > _CANDIDATE_NAME_MAX_LEN:
        return False
    if re.match(r"^https?://", t, re.I):
        return False
    low = t.lower()
    if any(j in low for j in _UI_JUNK_SUBSTRINGS) and len(t) < 28:
        return False
    if low in {"ok", "yes", "no", "on", "off"}:
        return False
    return True


def _iter_json_objects(blob: str) -> list[dict[str, Any]]:
    """observation blob 안의 JSON 객체 수집 (중첩 summary·UIA)."""
    found: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def _add(obj: dict[str, Any]) -> None:
        key = json.dumps(obj, sort_keys=True, ensure_ascii=False)[:200]
        if key in seen_keys:
            return
        seen_keys.add(key)
        found.append(obj)

    for line in blob.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            _add(obj)

    for chunk in re.findall(r"\{[^{}]*\"summary\"[^{}]*\}", blob):
        try:
            meta = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(meta, dict):
            _add(meta)

    # UIA payload: window + elements (긴 JSON 한 덩어리)
    for m in re.finditer(r'\{"window"[^}]*"elements"\s*:\s*\[', blob):
        start = m.start()
        depth = 0
        for i in range(start, min(start + 12000, len(blob))):
            ch = blob[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(blob[start : i + 1])
                        if isinstance(obj, dict):
                            _add(obj)
                    except json.JSONDecodeError:
                        pass
                    break
    return found


def _candidates_from_uia_object(obj: dict[str, Any]) -> list[str]:
    """UIA elements 배열에서 제목 후보 추출 (순서 유지 = 상위 결과 우선)."""
    out: list[str] = []
    seen: set[str] = set()
    elements = obj.get("elements")
    if not isinstance(elements, list):
        return out
    preferred_types = ("hyperlink", "listitem", "text", "document", "button")
    typed: list[tuple[int, str]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        name = str(el.get("name") or "").strip()
        if not _is_usable_candidate_name(name):
            continue
        ctype = str(el.get("type") or "").lower()
        # Button/Edit/Menu는 Chrome UI 라벨 — 제목 후보 제외
        if any(t in ctype for t in ("button", "edit", "menu")):
            continue
        prio = 2
        if any(p in ctype for p in preferred_types):
            prio = 0
        elif ctype in ("pane", "unknown"):
            prio = 3
        typed.append((prio, name))
    typed.sort(key=lambda x: x[0])
    for _, name in typed:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _candidates_from_summary_text(text: str) -> list[str]:
    """OCR/hybrid summary 텍스트에서 줄 단위 후보."""
    out: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[\n|•·]+", text):
        p = part.strip()
        if not _is_usable_candidate_name(p):
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def extract_result_candidates(
    observation_blob: str,
    *,
    max_items: int = _PLAY_CANDIDATE_MAX,
) -> list[str]:
    """perceive 요약에서 재생 후보 상위 N개 (UIA JSON 우선, OCR 줄 단위 보조)."""
    candidates: list[str] = []
    seen: set[str] = set()

    def _append_batch(names: list[str]) -> None:
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            candidates.append(n)
            if len(candidates) >= max_items:
                return

    for obj in _iter_json_objects(observation_blob):
        summ = obj.get("summary")
        if isinstance(summ, str) and summ.strip().startswith("{"):
            try:
                inner = json.loads(summ)
                if isinstance(inner, dict):
                    _append_batch(_candidates_from_uia_object(inner))
                    if len(candidates) >= max_items:
                        return candidates[:max_items]
            except json.JSONDecodeError:
                pass
        if isinstance(summ, str):
            _append_batch(_candidates_from_summary_text(summ))
            if len(candidates) >= max_items:
                return candidates[:max_items]
        _append_batch(_candidates_from_uia_object(obj))
        if len(candidates) >= max_items:
            return candidates[:max_items]

    for line in observation_blob.splitlines():
        t = line.strip()
        if len(t) < 3:
            continue
        low = t.lower()
        if any(low.startswith(p) for p in _SKIP_LINE_PREFIXES):
            continue
        if not _is_usable_candidate_name(t):
            continue
        _append_batch([t])
        if len(candidates) >= max_items:
            return candidates[:max_items]

    return candidates[:max_items]


def _ranker_screenshot_enabled(settings: object | None) -> bool:
    """Settings·테스트용 SimpleNamespace 모두 지원."""
    if settings is None:
        return False
    if isinstance(settings, Settings):
        return settings.media_ranker_use_screenshot
    return bool(getattr(settings, "media_ranker_use_screenshot", False))


def _ranker_vision_model_name(settings: object | None) -> str | None:
    if settings is None:
        return None
    if isinstance(settings, Settings):
        return settings.media_ranker_vision_model or settings.gemma_model_name
    vision = str(getattr(settings, "media_ranker_vision_model", "") or "").strip()
    base = str(getattr(settings, "gemma_model_name", "") or "").strip()
    return vision or base or None


def _settings_gemma_backend(settings: object | None) -> str:
    if isinstance(settings, Settings):
        return settings.gemma_backend
    return str(getattr(settings, "gemma_backend", "ollama") or "ollama")


def resolve_ranker_pick(
    rank: MediaRankerResult,
    candidates: list[str],
) -> str | None:
    """Ranker 출력을 실제 uia_click name으로 해석 (인덱스·fuzzy)."""
    if not candidates:
        return None
    if rank.pick_index is not None and 0 <= rank.pick_index < len(candidates):
        return candidates[rank.pick_index]
    pick = (rank.pick_name or "").strip()
    if not pick:
        return None
    if pick in candidates:
        return pick
    pl = pick.lower()
    for c in candidates:
        cl = c.lower()
        if pl == cl or pl in cl or cl in pl:
            return c
    pick_tokens = set(re.findall(r"[\w가-힣]+", pl))
    if not pick_tokens:
        return None
    best: tuple[float, str] | None = None
    for c in candidates:
        ct = set(re.findall(r"[\w가-힣]+", c.lower()))
        if not ct:
            continue
        overlap = len(pick_tokens & ct) / max(len(pick_tokens), 1)
        if best is None or overlap > best[0]:
            best = (overlap, c)
    if best and best[0] >= 0.35:
        return best[1]
    return None


# 하위 호환 — 테스트·외부 import
code_verify_search = mechanical_search_achieved
code_verify_play = mechanical_play_achieved


class MediaPlaybackFlow:
    """플랫폼별 Open → Perceive → (Select) → Act → Verify."""

    def __init__(self, cu_agent: ComputerUseAgent) -> None:
        self._agent = cu_agent
        self._gemma = cu_agent._gemma
        self._registry = cu_agent._registry
        self._assistant = cu_agent._assistant
        self._last_resolved_window: ResolvedMediaWindow | None = None
        # YouTube DOM 경로가 None으로 끝날 때 원인 — 레거시 실패 멘트에 반영
        self._media_dom_fail_hint: str | None = None

    def _consume_dom_fail_outcome(
        self,
        platform: str,
        fallback: MediaPlayOutcome,
    ) -> MediaPlayOutcome:
        """유튜브 DOM 티어가 실패한 뒤 레거시 분기에서 더 구체적인 outcome 선택."""
        if platform != "youtube":
            return fallback
        h = self._media_dom_fail_hint
        if not h:
            return fallback
        table: dict[str, MediaPlayOutcome] = {
            "no_browser_monitor": MediaPlayOutcome.YOUTUBE_DOM_SKIPPED_NO_MONITOR,
            "dom_empty_poll": MediaPlayOutcome.YOUTUBE_DOM_EMPTY_AFTER_POLL,
            "dom_parse_empty": MediaPlayOutcome.YOUTUBE_DOM_PARSE_EMPTY,
            "dom_pick_fail": MediaPlayOutcome.YOUTUBE_DOM_PICK_FAIL,
            "dom_open_watch_fail": MediaPlayOutcome.YOUTUBE_DOM_OPEN_WATCH_FAIL,
            "dom_verify_fail_play": MediaPlayOutcome.YOUTUBE_DOM_VERIFY_FAIL_PLAY,
        }
        mapped = table.get(h)
        self._media_dom_fail_hint = None
        return mapped or fallback

    def _finalize_media_reply(
        self,
        outcome: MediaPlayOutcome,
        goal: str,
        query: str,
        platform: str,
        action: str,
        *,
        tier_path: tuple[str, ...] | list[str],
        metrics: dict[str, Any] | None = None,
        log_tags: tuple[str, ...] | list[str] | None = None,
    ) -> str:
        """구조화 outcome → 로컬 LLM 멘트(폴백 포함)."""
        return media_reply_from_context(
            self._gemma,
            goal=goal,
            query=query,
            platform=platform,
            action=action,
            outcome=outcome,
            tier_path=list(tier_path),
            metrics=dict(metrics or {}),
            log_tags=list(log_tags or []),
        )

    def run(self, goal: str, slots: dict[str, Any]) -> str:
        goal = goal.strip()
        platform = str(slots.get("platform_hint") or "unknown").strip().lower()
        action = str(slots.get("media_action") or "").strip().lower()
        query = str(slots.get("search_query") or "").strip()
        if not query or action not in {"search", "play"}:
            return self._finalize_media_reply(
                MediaPlayOutcome.QUERY_MISSING,
                goal,
                query,
                platform,
                action,
                tier_path=("run",),
                metrics={"slots_search_query": bool(query.strip())},
                log_tags=("entry_validation",),
            )
        self._media_dom_fail_hint = None
        db = self._assistant._db
        db.insert_log("media_flow", "start", f"{platform}/{action} {query[:80]}")
        self._log(platform, action, "start")
        try:
            open_url = build_media_open_url(platform, query)
        except ValueError:
            return self._finalize_media_reply(
                MediaPlayOutcome.SEARCH_QUERY_NEEDED,
                goal,
                query,
                platform,
                action,
                tier_path=("run", "build_open_url"),
                log_tags=("value_error_media_url",),
            )
        self._log(platform, action, "open")
        should_open_url = True
        cached_pairs: list[tuple[str, str]] = []
        ingest_baseline: int | None = None
        monitor = self._browser_monitor()
        if platform == "youtube" and action == "play" and monitor is not None:
            try:
                ingest_baseline = monitor.total_ingest_count()
            except Exception:
                ingest_baseline = 0
            try:
                cached = monitor.youtube_results_for_search(open_url)
            except Exception:
                cached = None
            if cached:
                cached_pairs = list(cached)
                should_open_url = False
        if should_open_url:
            open_res = self._run_tool(
                "open_url", {"url": open_url}, summary=f"media open {platform}"
            )
            if not open_res.success:
                db.insert_log("media_flow", "open_fail", open_res.message[:200])
                return self._finalize_media_reply(
                    MediaPlayOutcome.OPEN_URL_FAIL,
                    goal,
                    query,
                    platform,
                    action,
                    tier_path=("run", "open_url"),
                    metrics={"tool_message_chars": len(open_res.message or "")},
                    log_tags=("open_url_fail",),
                )
        else:
            self._log(
                platform,
                action,
                "open_skip_cached",
                extra=f"youtube_dom_candidates={len(cached_pairs)}",
            )

        contract = resolve_media_contract(slots=slots)
        criteria_str = contract.value if contract else criteria_value_from_slots(slots)
        self._assistant._db.insert_log(
            "media_flow",
            "criteria",
            criteria_str[:80] if criteria_str else f"derive:{action}",
        )

        if action == "search":
            self._log(platform, action, "perceive")
            obs_blob = self._perceive(platform, open_url=open_url)
            if self._verify_search(
                goal, platform, query, obs_blob, criteria=contract
            ):
                clear_last_execution_hint(self._assistant)
                msg = self._finalize_media_reply(
                    MediaPlayOutcome.SUCCESS_SEARCH_OPEN,
                    goal,
                    query,
                    platform,
                    action,
                    tier_path=("search", "verify_ok"),
                    log_tags=("search_complete",),
                )
                db.insert_log("media_flow", "complete", msg[:200])
                self._log(platform, action, "complete")
                self._save_session(
                    goal,
                    query,
                    tools=["open_url", "perceive_desktop"],
                    media_action="search",
                )
                return msg
            db.insert_log("media_flow", "verify_fail", "search")
            set_last_execution_hint(self._assistant, "media:search:verify_fail")
            push_activity_line("skill=media_play gate=fail")
            return self._finalize_media_reply(
                MediaPlayOutcome.SEARCH_VERIFY_FAIL,
                goal,
                query,
                platform,
                action,
                tier_path=("search", "verify_fail"),
                log_tags=("search_verify_fail",),
            )
        if platform == "youtube":
            dom_msg = self._run_youtube_dom_play_path(
                goal,
                platform,
                query,
                db,
                open_url=open_url,
                criteria=contract,
                ingest_baseline=ingest_baseline,
                opened_search_url=should_open_url,
            )
            if dom_msg:
                return dom_msg
        return self._run_play_path(
            goal, platform, query, db, open_url=open_url, criteria=contract
        )

    def _browser_monitor(self) -> Any | None:
        """MainWindow가 주입한 Chrome 탭 모니터 (없으면 DOM 경로 스킵)."""
        return getattr(self._assistant, "_browser_monitor", None)

    def _run_youtube_dom_play_path(
        self,
        goal: str,
        platform: str,
        query: str,
        db: Any,
        *,
        open_url: str = "",
        criteria: MediaSuccessCriteria | None = None,
        ingest_baseline: int | None = None,
        opened_search_url: bool = True,
    ) -> str | None:
        """Tier 1: 확장 DOM → watch open_url → verify. 실패 시 None(legacy 폴백)."""
        monitor = self._browser_monitor()
        if monitor is None:
            self._media_dom_fail_hint = "no_browser_monitor"
            return None
        contract = criteria or MediaSuccessCriteria.PLAYBACK_CONFIRMED
        ingest_age_sec: float | None = None
        if hasattr(monitor, "last_ingest_age_seconds"):
            try:
                ingest_age_sec = monitor.last_ingest_age_seconds()
            except Exception:
                ingest_age_sec = None
        self._log(platform, "play", "dom_wait")
        after_count = ingest_baseline if opened_search_url else None
        raw_pairs: list[tuple[str, str]] | None = None
        if hasattr(monitor, "wait_for_youtube_search_results"):
            raw_pairs = monitor.wait_for_youtube_search_results(
                open_url,
                timeout_sec=_YOUTUBE_DOM_WAIT_TIMEOUT_SEC,
                after_ingest_count=after_count,
            )
        else:
            raw_pairs = monitor.youtube_results_for_search(open_url)
        if raw_pairs:
            self._log(platform, "play", "dom_wait_ok")
        else:
            self._log(platform, "play", "dom_wait_timeout")
        if not raw_pairs:
            db.insert_log("youtube_dom", "empty", f"query={query[:60]}")
            self._media_dom_fail_hint = "dom_empty_poll"
            return None
        dom_candidates = parse_youtube_search_results(
            [{"title": t, "url": u} for t, u in raw_pairs]
        )
        if not dom_candidates:
            db.insert_log("youtube_dom", "parse_empty", f"pairs={len(raw_pairs)}")
            self._media_dom_fail_hint = "dom_parse_empty"
            return None
        db.insert_log(
            "youtube_dom",
            "candidates",
            f"count={len(dom_candidates)} query={query[:40]}",
        )
        self._log(platform, "play", "dom_pick")

        def _rank_titles(titles: list[str]) -> str | None:
            rank = self._rank(
                goal,
                query,
                titles,
                screenshot_png=self._capture_play_verify_screenshot(platform),
                platform=platform,
            )
            if not rank:
                return None
            return resolve_ranker_pick(rank, titles)

        picked: YoutubeWatchCandidate | None = pick_watch_url(
            query,
            dom_candidates,
            rank_pick_title=_rank_titles,
        )
        if not picked:
            db.insert_log("youtube_dom", "pick_fail", f"candidates={len(dom_candidates)}")
            self._media_dom_fail_hint = "dom_pick_fail"
            return None
        vid = extract_video_id(picked.url)
        db.insert_log(
            "youtube_dom",
            "picked",
            f"videoId={vid} title={picked.title[:80]} url={picked.url[:120]}",
        )
        self._log(platform, "play", "dom_open_watch")
        navigated = self._navigate_current_tab_to_url(platform, picked.url)
        if not navigated:
            watch_res = self._run_tool(
                "open_url",
                {"url": picked.url},
                summary="media dom watch",
            )
            if not watch_res.success:
                db.insert_log("youtube_dom", "open_watch_fail", watch_res.message[:120])
                self._media_dom_fail_hint = "dom_open_watch_fail"
                return None
        obs_after = self._perceive(platform, open_url=picked.url, for_play=True)
        for mech_try in range(_MAX_MECHANICAL_PERCEIVE_RETRY + 1):
            if criteria_satisfied(
                contract,
                MediaExecutionPhase.PLAY_DONE,
                platform=platform,
                query=query,
                observation_blob=obs_after,
            ):
                clear_last_execution_hint(self._assistant)
                self._media_dom_fail_hint = None
                msg = self._finalize_media_reply(
                    MediaPlayOutcome.SUCCESS_PLAY_DOM,
                    goal,
                    query,
                    platform,
                    "play",
                    tier_path=("youtube_dom", "open_watch", "mechanical_play_ok"),
                    metrics={
                        "video_id": vid or "",
                        "last_ingest_age_sec": ingest_age_sec,
                    },
                    log_tags=("dom_play_complete",),
                )
                db.insert_log("media_flow", "complete", f"dom|{msg[:120]}")
                self._log(platform, "play", "complete_dom")
                self._save_session(
                    goal,
                    query,
                    tools=["open_url", "open_url", "perceive_desktop"],
                    media_action="play",
                )
                return msg
            if mech_try < _MAX_MECHANICAL_PERCEIVE_RETRY:
                obs_after = self._perceive(platform, open_url=picked.url, for_play=True)
        verify_shot = self._capture_play_verify_screenshot(platform)
        verify, verify_vision_used = verify_media_with_llm_retries(
            self._gemma,
            goal=goal,
            media_action="play",
            observation_blob=obs_after,
            screenshot_png=verify_shot,
        )
        db.insert_log(
            "media_flow",
            "verify_play",
            json.dumps(
                {
                    "path": "dom",
                    "vision_used": verify_vision_used,
                    "achieved": bool(verify and verify.achieved),
                    "videoId": vid,
                },
                ensure_ascii=False,
            )[:_RANK_LOG_JSON_MAX],
        )
        if verify and verify.achieved:
            clear_last_execution_hint(self._assistant)
            self._media_dom_fail_hint = None
            msg = self._finalize_media_reply(
                MediaPlayOutcome.SUCCESS_PLAY_DOM_LLM,
                goal,
                query,
                platform,
                "play",
                tier_path=("youtube_dom", "open_watch", "llm_verify_ok"),
                metrics={
                    "video_id": vid or "",
                    "vision_used": verify_vision_used,
                },
                log_tags=("dom_play_llm_complete",),
            )
            db.insert_log("media_flow", "complete", f"dom_llm|{vid}")
            self._log(platform, "play", "complete_dom_llm")
            self._save_session(
                goal,
                query,
                tools=["open_url", "open_url", "perceive_desktop"],
                media_action="play",
            )
            return msg
        db.insert_log("youtube_dom", "verify_fail", vid or "unknown")
        self._media_dom_fail_hint = "dom_verify_fail_play"
        return None

    def _navigate_current_tab_to_url(self, platform: str, url: str) -> bool:
        """open_url 대신 현재 탭 주소창으로 이동(새 탭 노출 감소)."""
        if not url:
            return False

        target = resolve_media_target(platform)
        wins = window_controller.list_visible_windows()
        chosen_hwnd = 0
        for w in wins:
            title = (w.title or "").lower()
            if target.window_title_sub.lower() in title:
                chosen_hwnd = int(getattr(w, "hwnd", 0) or 0)
                break
        if chosen_hwnd <= 0 and target.alt_title_subs:
            for alt in target.alt_title_subs:
                for w in wins:
                    title = (w.title or "").lower()
                    if alt.lower() in title:
                        chosen_hwnd = int(getattr(w, "hwnd", 0) or 0)
                        break
                if chosen_hwnd > 0:
                    break
        # YouTube 창을 특정하지 못하면 다른 앱에 Ctrl+L이 들어갈 수 있어
        # 안전하게 실패 후 open_url fallback으로 넘깁니다.
        if chosen_hwnd <= 0:
            return False
        window_controller.focus_window_by_hwnd(chosen_hwnd)

        def _foreground_is_target() -> bool:
            if chosen_hwnd <= 0:
                return True
            try:
                import win32gui  # type: ignore

                return int(win32gui.GetForegroundWindow() or 0) == chosen_hwnd
            except Exception:
                return True

        wait_until(_foreground_is_target, timeout_sec=_ADDRBAR_FOCUS_WAIT_SEC)

        hk1 = self._run_tool(
            "send_hotkey",
            {"keys": ["ctrl", "l"]},
            summary="media dom addrbar ctrl+l",
        )
        if not hk1.success:
            return False
        it = self._run_tool(
            "type_text",
            {"text": url},
            summary="media dom addrbar url",
        )
        if not it.success:
            return False
        hk2 = self._run_tool(
            "send_hotkey",
            {"keys": ["enter"]},
            summary="media dom addrbar enter",
        )
        return hk2.success

    def _run_play_path(
        self,
        goal: str,
        platform: str,
        query: str,
        db: Any,
        *,
        open_url: str = "",
        criteria: MediaSuccessCriteria | None = None,
    ) -> str:
        """play — perceive → ranker(상위 N 자동 선택) → click → verify (의도적 sleep 없음)."""
        contract = criteria or MediaSuccessCriteria.PLAYBACK_CONFIRMED
        self._log(platform, "play", "perceive_loop")
        obs_blob, candidates, gate_ready, last_raw_n, last_filt_n = (
            self._perceive_for_play(
                platform, query, open_url=open_url, criteria=contract
            )
        )
        degraded = (not gate_ready) and len(candidates) >= 1
        if not candidates:
            db.insert_log(
                "media_flow",
                "gate_fail",
                f"candidates={len(candidates)} ready={gate_ready}",
            )
            self._log(
                platform,
                "play",
                "gate_fail",
                extra=f"candidates={len(candidates)}",
            )
            set_last_execution_hint(self._assistant, "media:pre_rank:no_candidates")
            push_activity_line("skill=media_play gate=fail")
            outcome = self._consume_dom_fail_outcome(
                platform, MediaPlayOutcome.LEGACY_GATE_NO_CANDIDATES
            )
            return self._finalize_media_reply(
                outcome,
                goal,
                query,
                platform,
                "play",
                tier_path=("legacy_uia", "pre_rank_gate_fail"),
                metrics={
                    "filtered_candidates": len(candidates),
                    "raw_candidates_hint": last_raw_n,
                    "last_filt_candidates": last_filt_n,
                    "gate_ready": gate_ready,
                },
                log_tags=("perceive_gate_fail",),
            )
        if degraded:
            set_last_execution_hint(self._assistant, "media:pre_rank:degraded")
            self._log(platform, "play", "degraded", extra=f"candidates={len(candidates)}")
            push_activity_line("skill=media_play pre_rank=degraded")
        self._log(platform, "play", "rank")
        screenshot_png = self._capture_play_verify_screenshot(platform)
        db.insert_log(
            "media_flow",
            "rank_input",
            json.dumps(
                {"query": query[:80], "candidates": candidates},
                ensure_ascii=False,
            )[:_RANK_LOG_JSON_MAX],
        )
        shot_hwnd = (
            self._last_resolved_window.hwnd if self._last_resolved_window else 0
        )
        if screenshot_png:
            w, h = 0, 0
            try:
                from PIL import Image  # type: ignore
                import io

                im = Image.open(io.BytesIO(screenshot_png))
                w, h = im.size
            except Exception:
                w, h = 0, 0
            db.insert_log(
                "media_flow",
                "rank_screenshot",
                f"hwnd={shot_hwnd} sent=true size={w}x{h}",
            )
        else:
            db.insert_log(
                "media_flow",
                "rank_screenshot",
                f"hwnd={shot_hwnd} sent=false",
            )
        rank = self._rank(
            goal,
            query,
            candidates,
            screenshot_png=screenshot_png,
            platform=platform,
        )
        if rank:
            db.insert_log(
                "media_flow",
                "rank_output",
                json.dumps(
                    {
                        "query": query[:80],
                        "pick_index": rank.pick_index,
                        "pick_name": rank.pick_name,
                        "confidence": rank.confidence,
                        "reason": rank.reason[:200],
                    },
                    ensure_ascii=False,
                )[:_RANK_LOG_JSON_MAX],
            )
        click_name = resolve_ranker_pick(rank, candidates) if rank else None

        if not click_name and candidates:
            click_name = mechanical_pick_candidate(candidates, query)
            if click_name:
                db.insert_log(
                    "media_flow",
                    "rank_fallback",
                    f"mechanical={click_name[:80]}",
                )
                self._log(platform, "play", "rank_fallback")

        if not click_name:
            low_conf = rank is not None and rank.confidence < _RANKER_AUTO_PLAY_MIN_CONFIDENCE
            log_tags_extra: tuple[str, ...] = ()
            metrics: dict[str, Any] = {"low_conf_ranker": low_conf}
            if rank:
                metrics["rank_confidence"] = rank.confidence
                rn = (rank.reason or "").strip()
                if rn:
                    metrics["ranker_hint"] = rn[:120]
            if rank and rank.pick_name:
                log_tags_extra = ("ranker_null_pick_after_resolve",)

            outcome = self._consume_dom_fail_outcome(
                platform, MediaPlayOutcome.LEGACY_RANK_ASK_USER
            )
            return self._finalize_media_reply(
                outcome,
                goal,
                query,
                platform,
                "play",
                tier_path=(
                    "legacy_uia",
                    "rank_no_click",
                    *(("low_confidence",) if low_conf else ()),
                ),
                metrics={
                    **metrics,
                    "candidates_kept": len(candidates),
                },
                log_tags=("rank_pick_unresolved", *log_tags_extra),
            )

        db.insert_log(
            "media_flow",
            "rank_pick",
            f"query={query[:40]} click_name={click_name[:120]}",
        )

        resolved = self._last_resolved_window
        click_sub = (
            resolved.title_sub
            if resolved
            else resolve_media_target(platform).window_title_sub
        )
        self._log(platform, "play", "act")
        click_ok = self._click_with_retry(click_sub, click_name)
        if not click_ok:
            self._log(platform, "play", "hotkey_fallback")
            click_ok = self._play_keyboard_fallback(platform)
        if not click_ok:
            db.insert_log("media_flow", "click_fail", click_name[:120])
            outcome = self._consume_dom_fail_outcome(
                platform, MediaPlayOutcome.LEGACY_CLICK_FAIL
            )
            return self._finalize_media_reply(
                outcome,
                goal,
                query,
                platform,
                "play",
                tier_path=("legacy_uia", "uia_click_fail"),
                metrics={"attempted_click_name_chars": len(click_name)},
                log_tags=("click_fail",),
            )
        obs_after = self._perceive(platform, open_url=open_url)
        for mech_try in range(_MAX_MECHANICAL_PERCEIVE_RETRY + 1):
            if criteria_satisfied(
                contract,
                MediaExecutionPhase.PLAY_DONE,
                platform=platform,
                query=query,
                observation_blob=obs_after,
            ):
                clear_last_execution_hint(self._assistant)
                msg = self._finalize_media_reply(
                    MediaPlayOutcome.SUCCESS_PLAY_LEGACY,
                    goal,
                    query,
                    platform,
                    "play",
                    tier_path=("legacy_uia", "mechanical_play_ok"),
                    log_tags=("legacy_play_complete",),
                )
                db.insert_log("media_flow", "complete", msg[:200])
                self._log(platform, "play", "complete")
                self._save_session(
                    goal,
                    query,
                    tools=["open_url", "perceive_desktop", "uia_click"],
                    media_action="play",
                )
                return msg
            if mech_try < _MAX_MECHANICAL_PERCEIVE_RETRY:
                self._log(platform, "play", "perceive_retry")
                obs_after = self._perceive(platform, open_url=open_url)
        verify_shot = self._capture_play_verify_screenshot(platform)
        verify, verify_vision_used = verify_media_with_llm_retries(
            self._gemma,
            goal=goal,
            media_action="play",
            observation_blob=obs_after,
            screenshot_png=verify_shot,
        )
        db.insert_log(
            "media_flow",
            "verify_play",
            json.dumps(
                {
                    "vision_used": verify_vision_used,
                    "achieved": bool(verify and verify.achieved),
                    "evidence": (verify.evidence if verify else "")[:120],
                    "missing": (verify.missing if verify else "")[:120],
                },
                ensure_ascii=False,
            )[:_RANK_LOG_JSON_MAX],
        )
        if verify and verify.achieved:
            clear_last_execution_hint(self._assistant)
            msg = self._finalize_media_reply(
                MediaPlayOutcome.SUCCESS_PLAY_LEGACY_LLM,
                goal,
                query,
                platform,
                "play",
                tier_path=("legacy_uia", "llm_verify_ok"),
                metrics={"vision_used": verify_vision_used},
                log_tags=("legacy_play_llm_complete",),
            )
            db.insert_log("media_flow", "complete", f"llm|{verify.evidence[:120]}")
            self._log(platform, "play", "complete_llm")
            self._save_session(
                goal,
                query,
                tools=["open_url", "perceive_desktop", "uia_click"],
                media_action="play",
            )
            return msg
        db.insert_log("media_flow", "verify_fail", "play")
        set_last_execution_hint(self._assistant, "media:play:not_confirmed")
        push_activity_line("skill=media_play gate=fail")
        outcome = self._consume_dom_fail_outcome(
            platform, MediaPlayOutcome.LEGACY_VERIFY_FAIL_PLAY
        )
        return self._finalize_media_reply(
            outcome,
            goal,
            query,
            platform,
            "play",
            tier_path=("legacy_uia", "play_verify_fail"),
            metrics={
                "vision_used": verify_vision_used,
                "verify_missing_len": len((verify.missing if verify else "") or ""),
            },
            log_tags=("verify_play_fail",),
        )

    def _perceive_for_play(
        self,
        platform: str,
        query: str,
        *,
        open_url: str = "",
        criteria: MediaSuccessCriteria | None = None,
    ) -> tuple[str, list[str], bool, int, int]:
        """타깃 perceive — 의도적 대기 제거, 실패 시 sleep 없이 perceive만 재시도."""
        contract = criteria or MediaSuccessCriteria.PLAYBACK_CONFIRMED
        self._last_resolved_window = None
        obs = ""
        candidates: list[str] = []
        last_raw_n = 0
        last_filt_n = 0
        db = self._assistant._db
        gate_ready = False
        for attempt in range(_PERCEIVE_LOAD_MAX_RETRIES):
            if attempt > 0:
                # sleep 없음 — 즉시 다음 perceive
                self._log(platform, "play", f"perceive_retry_{attempt}")
            obs = self._perceive(platform, open_url=open_url, for_play=True)
            raw_candidates = extract_result_candidates(obs)
            last_raw_n = len(raw_candidates)
            candidates = filter_video_title_candidates(
                filter_media_candidates(
                    raw_candidates,
                    platform=platform,
                    search_query=query,
                    require_query_token_overlap=False,
                ),
                platform=platform,
                search_query=query,
            )
            last_filt_n = len(candidates)
            ready = criteria_satisfied(
                contract,
                MediaExecutionPhase.PRE_RANK,
                platform=platform,
                query=query,
                observation_blob=obs,
                candidates=candidates,
            )
            gate_ready = ready
            target_sub = (
                self._last_resolved_window.title_sub[:24]
                if self._last_resolved_window
                else resolve_media_target(platform).window_title_sub[:24]
            )
            gate_tag = "pass" if ready else "fail"
            db.insert_log(
                "media_flow",
                "perceive_gate",
                (
                    f"target={target_sub} "
                    f"raw={len(raw_candidates)} filt={len(candidates)} gate={gate_tag}"
                )[:200],
            )
            self._log(
                platform,
                "play",
                f"perceive_gate_{gate_tag}",
                extra=f"candidates={len(candidates)}",
            )
            if ready:
                return obs, candidates, True, last_raw_n, last_filt_n
        return obs, candidates, gate_ready, last_raw_n, last_filt_n

    def _verify_search(
        self,
        goal: str,
        platform: str,
        search_query: str,
        observation_blob: str,
        *,
        criteria: MediaSuccessCriteria | None = None,
    ) -> bool:
        contract = criteria or MediaSuccessCriteria.SEARCH_RESULTS_VISIBLE
        if criteria_satisfied(
            contract,
            MediaExecutionPhase.SEARCH_DONE,
            platform=platform,
            query=search_query,
            observation_blob=observation_blob,
        ):
            return True
        verify, _vision_used = verify_media_with_llm_retries(
            self._gemma,
            goal=goal,
            media_action="search",
            observation_blob=observation_blob,
            max_attempts=2,
        )
        return bool(verify and verify.achieved)

    def _log(
        self,
        platform: str,
        action: str,
        step: str,
        *,
        extra: str = "",
    ) -> None:
        line = f"MediaFlow: platform={platform} action={action} step={step}"
        if extra:
            line += f" {extra}"
        push_activity_line(line)

    def _save_session(
        self,
        goal: str,
        query: str,
        *,
        tools: list[str],
        media_action: str,
    ) -> None:
        obs = [f"search_query={query[:80]}"]
        if media_action == "play":
            obs.append(format_media_verify_ok("play"))
        self._assistant.memory.save_task_session(
            goal[:200],
            tools_run=tools,
            observations=obs,
        )

    def _focus_resolved_window(
        self,
        resolved: ResolvedMediaWindow,
        platform: str,
    ) -> None:
        """점수화로 고른 창 포커스 — hwnd 우선, 실패 시 title_sub."""
        if resolved.hwnd > 0 and window_controller.focus_window_by_hwnd(resolved.hwnd):
            self._log(
                platform,
                "media",
                "focus_ok",
                extra=f"hwnd={resolved.hwnd} reason={resolved.match_reason[:40]}",
            )
            return
        res = self._run_tool(
            "focus_window",
            {"title_sub": resolved.title_sub},
            summary=f"media focus {resolved.title_sub[:24]}",
        )
        if res.success:
            self._log(
                platform,
                "media",
                "focus_ok",
                extra=f"target={resolved.title_sub[:24]} reason={resolved.match_reason[:32]}",
            )
            return
        self._log(
            platform,
            "media",
            "focus_skip",
            extra=f"reason={resolved.match_reason[:32]}",
        )

    def _focus_media_target(self, target: MediaTarget, platform: str) -> None:
        """타깃 창 포커스 — 실패해도 perceive는 계속 (fallback)."""
        subs: list[str] = []
        if target.window_title_sub:
            subs.append(target.window_title_sub)
        for alt in target.alt_title_subs:
            if alt not in subs:
                subs.append(alt)
        for sub in subs:
            res = self._run_tool(
                "focus_window",
                {"title_sub": sub},
                summary=f"media focus {sub[:24]}",
            )
            if res.success:
                self._log(platform, "media", "focus_ok", extra=f"target={sub[:24]}")
                return
        self._log(platform, "media", "focus_skip")

    def _perceive(
        self,
        platform: str = "unknown",
        *,
        open_url: str = "",
        for_play: bool = False,
    ) -> str:
        """타깃 포커스 후 list_open_windows + perceive_desktop (resolved window 우선)."""
        target = resolve_media_target(platform)
        parts: list[str] = []
        win = self._run_tool("list_open_windows", {}, summary="media windows")
        window_blob = ""
        if win.success:
            window_blob = (win.detail or win.message or "")[:600]
            parts.append(f"windows: {window_blob}")
        resolved = resolve_focus_window_after_open(
            platform,
            open_url=open_url,
            window_list_blob=window_blob,
        )
        if resolved:
            self._last_resolved_window = resolved
            if target.focus_before_perceive:
                self._focus_resolved_window(resolved, platform)
        elif target.focus_before_perceive:
            self._focus_media_target(target, platform)
        focus_sub = (
            resolved.title_sub if resolved else target.window_title_sub
        )
        perceive_params: dict[str, Any] = {
            "focus_hint": focus_sub,
            "window_title_sub": focus_sub,
        }
        if for_play:
            perceive_params["prefer_window_only"] = True
        pd = self._run_tool(
            "perceive_desktop",
            perceive_params,
            summary=f"media perceive {focus_sub[:20]}",
        )
        detail = ""
        if pd.success:
            parts.append(pd.message[:_PERCEIVE_MESSAGE_MAX])
            if pd.detail:
                raw_detail = pd.detail[:_PERCEIVE_DETAIL_MAX]
                if resolved:
                    raw_detail = _patch_perception_active_window(
                        raw_detail, resolved.title_sub
                    )
                detail = raw_detail
                parts.append(detail)
        else:
            parts.append(f"perceive: fail | {pd.message[:200]}")
        blob = "\n".join(parts)
        perceive_target = MediaTarget(
            focus_sub,
            url_domain_hint=target.url_domain_hint,
            alt_title_subs=target.alt_title_subs,
        )
        resolved_hwnd = resolved.hwnd if resolved else 0
        blob = self._maybe_window_ocr_augment(
            blob,
            detail,
            perceive_target,
            for_play=for_play,
            resolved_hwnd=resolved_hwnd,
        )
        reason = resolved.match_reason[:32] if resolved else "default_target"
        self._assistant._db.insert_log(
            "media_flow",
            "perceive",
            f"target={focus_sub[:24]} reason={reason}|{parts[-1][:180] if parts else ''}",
        )
        return blob

    def _maybe_window_ocr_augment(
        self,
        blob: str,
        detail: str,
        target: MediaTarget,
        *,
        for_play: bool = False,
        resolved_hwnd: int = 0,
    ) -> str:
        """UIA sparse·타깃 불일치 시 창 단위 OCR (play+hwnd면 1회 우선, 전체 화면 OCR 없음)."""
        settings = self._assistant._settings
        if not isinstance(settings, Settings):
            return blob
        if for_play and resolved_hwnd > 0:
            augmented = self._window_ocr_augment_blob(
                blob, target.window_title_sub, resolved_hwnd, settings
            )
            if augmented != blob:
                return augmented
        uia_json = ""
        perception_source = ""
        active = ""
        if detail:
            try:
                meta = json.loads(detail)
                if isinstance(meta, dict):
                    perception_source = str(meta.get("perception_source") or "")
                    active = str(meta.get("active_window") or "")
                    summ = meta.get("summary")
                    if isinstance(summ, str) and summ.strip().startswith("{"):
                        uia_json = summ
            except json.JSONDecodeError:
                pass
        target_ok = target.window_title_sub.lower() in active.lower()
        if not target_ok and target.alt_title_subs:
            target_ok = any(a.lower() in active.lower() for a in target.alt_title_subs)
        sparse = not uia_json or uia_reader.is_uia_summary_sparse(uia_json)
        need_ocr = sparse or perception_source in ("ocr", "hybrid", "") or not target_ok
        if not need_ocr:
            return blob
        hwnd = 0
        for sub in (target.window_title_sub, *target.alt_title_subs):
            wins = window_controller.find_windows_by_title_substring(sub)
            if wins and wins[0].hwnd > 0:
                hwnd = wins[0].hwnd
                break
        if hwnd <= 0:
            return blob
        return self._window_ocr_augment_blob(
            blob, target.window_title_sub, hwnd, settings
        )

    def _window_ocr_augment_blob(
        self,
        blob: str,
        active_window: str,
        hwnd: int,
        settings: Settings,
    ) -> str:
        cap = screen_capture.capture_window_by_hwnd(hwnd)
        if not cap:
            return blob
        raw = ocr_engine.ocr_image(settings, cap)
        summary, _ = ocr_engine.ocr_for_storage(settings, raw)
        if not summary.strip():
            return blob
        augment = json.dumps(
            {
                "perception_source": "window_ocr",
                "active_window": active_window,
                "summary": summary[:1800],
            },
            ensure_ascii=False,
        )
        return f"{blob}\n{augment}"

    def _play_keyboard_fallback(self, platform: str) -> bool:
        """uia_click 실패 시 tab/enter·down/enter (HIGH_RISK, Safety Guard 통과)."""
        ph = (platform or "unknown").strip().lower()
        sequences: list[list[str]] = [["tab"], ["tab"], ["enter"]]
        if ph == "youtube":
            sequences.append(["down", "enter"])
        for keys in sequences:
            res = self._run_tool(
                "send_hotkey",
                {"keys": keys},
                summary=f"media hotkey {'+'.join(keys)}",
            )
            if res.success:
                return True
        return False

    def _run_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        summary: str,
    ) -> AutomationToolResult:
        return self._agent.run_tool_recorded(
            tool_name,
            params,
            summary=summary[:200],
            approved=True,
        )

    def _capture_play_verify_screenshot(self, platform: str) -> bytes | None:
        """Ranker·play verify용 미디어 창 캡처 — 메모리 PNG만 (DB·디스크 저장 없음)."""
        settings = self._assistant._settings
        if not _ranker_screenshot_enabled(settings):
            return None
        hwnd = 0
        resolved = self._last_resolved_window
        if resolved and resolved.hwnd > 0:
            hwnd = resolved.hwnd
        else:
            target = resolve_media_target(platform)
            for sub in (target.window_title_sub, *target.alt_title_subs):
                wins = window_controller.find_windows_by_title_substring(sub)
                if wins and wins[0].hwnd > 0:
                    hwnd = wins[0].hwnd
                    break
        if hwnd <= 0:
            return None
        cap = screen_capture.capture_window_by_hwnd(hwnd)
        if not cap:
            return None
        return screen_capture.capture_result_to_png_bytes(cap)

    def _capture_rank_screenshot(self, platform: str) -> bytes | None:
        """하위 호환 — _capture_play_verify_screenshot 위임."""
        return self._capture_play_verify_screenshot(platform)

    def _rank(
        self,
        goal: str,
        search_query: str,
        candidates: list[str],
        *,
        screenshot_png: bytes | None = None,
        platform: str = "unknown",
    ) -> MediaRankerResult | None:
        top = candidates[:_PLAY_CANDIDATE_MAX]
        if not top:
            return MediaRankerResult(
                pick_name=None,
                pick_index=None,
                confidence=0.0,
                reason="검색 결과 후보를 화면에서 찾지 못했습니다. 잠시 후 다시 요청해 주세요.",
            )
        user_body = (
            f"goal: {goal}\n"
            f"search_query: {search_query}\n"
            f"candidates: {json.dumps(top, ensure_ascii=False)}\n"
            "위 candidates와 첨부 스크린샷을 함께 보고 pick_index·pick_name을 결정하세요.\n"
        )
        settings = self._assistant._settings
        db = self._assistant._db
        want_shot = _ranker_screenshot_enabled(settings)
        if want_shot and not screenshot_png:
            screenshot_png = self._capture_play_verify_screenshot(platform)
            if not screenshot_png:
                screenshot_png = self._capture_play_verify_screenshot(platform)
        use_shot = bool(screenshot_png)
        vision_model = _ranker_vision_model_name(settings) if use_shot else None
        images: tuple[bytes, ...] = (screenshot_png,) if screenshot_png else ()
        msgs = [
            ChatMessage("system", MEDIA_RESULT_RANKER_SYSTEM),
            ChatMessage("user", user_body, images=images),
        ]
        vision_used = False
        if images and hasattr(self._gemma, "chat_with_images"):
            raw, vision_used = self._gemma.chat_with_images(
                msgs,
                purpose=LlmPurpose.COMPUTER_USE,
                lane="computer_use",
                model_override=vision_model,
            )
            db.insert_log("media_flow", "rank_vision", f"used={vision_used}")
        elif want_shot:
            if _settings_gemma_backend(settings) == "openai_compatible":
                db.insert_log(
                    "media_flow",
                    "rank_vision",
                    "vision_unavailable=openai_compatible",
                )
                push_activity_line(
                    "MediaRanker: vision_unavailable backend=openai_compatible"
                )
            elif not images:
                db.insert_log(
                    "media_flow",
                    "rank_vision",
                    "used=false reason=screenshot_capture_failed",
                )
            raw = self._gemma.chat(
                msgs,
                purpose=LlmPurpose.COMPUTER_USE,
                lane="computer_use",
                model_override=vision_model,
            )
        else:
            db.insert_log("media_flow", "rank_vision", "used=false reason=disabled")
            raw = self._gemma.chat(
                msgs,
                purpose=LlmPurpose.COMPUTER_USE,
                lane="computer_use",
                model_override=vision_model,
            )
        if self._is_llm_unavailable(raw):
            return None
        return parse_media_ranker_json(raw)

    def _click_with_retry(self, window_title_sub: str, pick_name: str) -> bool:
        params = {"window_title_sub": window_title_sub, "name": pick_name}
        for attempt in range(2):
            res = self._run_tool(
                "uia_click",
                params,
                summary=f"media click {pick_name[:40]}",
            )
            if res.success:
                return True
            if attempt == 0:
                self._log("media", "play", "click_retry")
        return False

    @staticmethod
    def _is_llm_unavailable(text: str) -> bool:
        t = text.strip()
        return t == FALLBACK_KO or "로컬 언어 모델에 연결할 수 없습니다" in t
