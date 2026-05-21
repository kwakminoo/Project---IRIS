"""미디어 검색·재생 고정 단계 플로우 — 의도·선택·완료 판단은 LLM, URL·검증 게이트는 코드."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.ai.response_parser import extract_json_object
from iris.ai.thinking_policy import LlmPurpose
from iris.assistant.computer_use_agent import USER_QUESTION_PREFIX
from iris.assistant.media_verify import (
    _MAX_MECHANICAL_PERCEIVE_RETRY,
    format_media_verify_ok,
    mechanical_play_achieved,
    mechanical_search_achieved,
    verify_media_with_llm_retries,
)
from iris.automation.media_urls import build_media_open_url
from iris.automation.tool_types import AutomationToolResult
from iris.core.activity_sink import push_activity_line
if TYPE_CHECKING:
    from iris.assistant.computer_use_agent import ComputerUseAgent
MEDIA_RESULT_RANKER_SYSTEM = """당신은 Iris Media Result Ranker입니다.
검색 결과 후보 제목 목록 중 사용자 goal과 search_query에 가장 부합하는 항목 하나를 고르세요.
규칙:
- 후보 목록에 실제로 있는 문자열과 동일한 pick_name만 선택 (자동 교정·번역 금지).
- 적합한 항목이 없으면 pick_name은 null, reason에 ask_user 권고(한국어).
- JSON만 출력: {"pick_name": "문자열 또는 null", "confidence": 0.0~1.0, "reason": "한국어"}
"""
_WINDOW_TITLE_SUB: dict[str, str] = {
    "youtube": "YouTube",
    "spotify": "Spotify",
    "netflix": "Netflix",
    "browser": "Chrome",
    "unknown": "Chrome",
}
def should_run_media_flow(slots: dict[str, Any] | None) -> bool:
    """Router slots로 Media Flow 진입 여부."""
    if not slots:
        return False
    action = str(slots.get("media_action") or "").strip().lower()
    query = slots.get("search_query")
    return action in {"search", "play"} and isinstance(query, str) and bool(query.strip())
@dataclass(frozen=True)
class MediaRankerResult:
    pick_name: str | None
    confidence: float
    reason: str
def parse_media_ranker_json(raw: str) -> MediaRankerResult | None:
    data = extract_json_object(raw)
    if not data:
        return None
    pick_raw = data.get("pick_name")
    pick = pick_raw.strip() if isinstance(pick_raw, str) and pick_raw.strip() else None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(data.get("reason") or "").strip()
    return MediaRankerResult(pick_name=pick, confidence=conf, reason=reason)
def extract_result_candidates(observation_blob: str, *, max_items: int = 12) -> list[str]:
    """perceive 요약에서 후보 제목 추출 (UIA/OCR 한 줄 단위)."""
    candidates: list[str] = []
    seen: set[str] = set()
    skip_prefixes = (
        "perceive:",
        "windows:",
        "tool_",
        "goal:",
        "slots:",
        "recipe_hint:",
        "media_verify_ok:",
        "verify_required:",
    )
    for line in observation_blob.splitlines():
        t = line.strip()
        if len(t) < 3 or len(t) > 120:
            continue
        low = t.lower()
        if any(low.startswith(p) for p in skip_prefixes):
            continue
        if t in seen:
            continue
        seen.add(t)
        candidates.append(t)
        if len(candidates) >= max_items:
            break
    if candidates:
        return candidates
    for chunk in re.findall(r"\{[^{}]*\"summary\"[^{}]*\}", observation_blob):
        try:
            meta = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        summ = str(meta.get("summary") or "")
        for part in re.split(r"[\n|•·]", summ):
            p = part.strip()
            if 3 <= len(p) <= 120 and p not in seen:
                seen.add(p)
                candidates.append(p)
                if len(candidates) >= max_items:
                    return candidates
    return candidates
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
    def run(self, goal: str, slots: dict[str, Any]) -> str:
        goal = goal.strip()
        platform = str(slots.get("platform_hint") or "unknown").strip().lower()
        action = str(slots.get("media_action") or "").strip().lower()
        query = str(slots.get("search_query") or "").strip()
        if not query or action not in {"search", "play"}:
            return f"{USER_QUESTION_PREFIX} 어떤 곡·영상을 찾거나 재생할까요?"
        db = self._assistant._db
        db.insert_log("media_flow", "start", f"{platform}/{action} {query[:80]}")
        self._log(platform, action, "start")
        try:
            open_url = build_media_open_url(platform, query)
        except ValueError:
            return f"{USER_QUESTION_PREFIX} 검색어를 알려주시겠어요?"
        self._log(platform, action, "open")
        open_res = self._run_tool("open_url", {"url": open_url}, summary=f"media open {platform}")
        if not open_res.success:
            db.insert_log("media_flow", "open_fail", open_res.message[:200])
            return "미디어 페이지를 열지 못했습니다. 다시 요청해 주세요."
        self._log(platform, action, "perceive")
        obs_blob = self._perceive()
        if action == "search":
            if self._verify_search(goal, platform, query, obs_blob):
                msg = f"'{query}' 검색 결과를 열었습니다."
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
            return (
                "검색 페이지를 열었지만 결과 확인이 어렵습니다. "
                "화면을 확인하시거나 다시 요청해 주세요."
            )
        return self._run_play_path(goal, platform, query, db, obs_blob)

    def _run_play_path(
        self,
        goal: str,
        platform: str,
        query: str,
        db: Any,
        obs_blob: str,
    ) -> str:
        """play — ranker → click → 기계 게이트 → (재perceive) → LLM verify."""
        candidates = extract_result_candidates(obs_blob)
        self._log(platform, "play", "rank")
        rank = self._rank(goal, query, candidates)
        if not rank or not rank.pick_name:
            question = (rank.reason if rank and rank.reason else "") or (
                f"'{query}' 검색 결과에서 재생할 항목을 골라 주세요."
            )
            db.insert_log("media_flow", "ask_user", question[:200])
            return f"{USER_QUESTION_PREFIX} {question}"
        window_sub = _WINDOW_TITLE_SUB.get(platform) or _WINDOW_TITLE_SUB["unknown"]
        self._log(platform, "play", "act")
        click_ok = self._click_with_retry(window_sub, rank.pick_name)
        if not click_ok:
            db.insert_log("media_flow", "click_fail", rank.pick_name[:120])
            return (
                f"'{rank.pick_name}' 항목을 클릭하지 못했습니다. "
                "화면에서 직접 선택하시거나 다시 요청해 주세요."
            )
        obs_after = self._perceive()
        for mech_try in range(_MAX_MECHANICAL_PERCEIVE_RETRY + 1):
            if mechanical_play_achieved(platform, obs_after):
                msg = f"'{query}' 재생을 시작했습니다."
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
                obs_after = self._perceive()
        verify = verify_media_with_llm_retries(
            self._gemma,
            goal=goal,
            media_action="play",
            observation_blob=obs_after,
        )
        if verify and verify.achieved:
            msg = f"'{query}' 재생을 시작했습니다."
            db.insert_log("media_flow", "complete", f"llm|{verify.evidence[:120]}")
            self._log(platform, "play", "complete_llm")
            self._save_session(
                goal,
                query,
                tools=["open_url", "perceive_desktop", "uia_click"],
                media_action="play",
            )
            return msg
        reason = ""
        if verify and verify.missing:
            reason = verify.missing
        elif verify and verify.evidence:
            reason = verify.evidence
        db.insert_log("media_flow", "verify_fail", "play")
        tail = f" ({reason})" if reason else ""
        return (
            "재생 화면을 확인하지 못했습니다. "
            f"브라우저에서 재생 상태를 확인하시거나 다시 요청해 주세요.{tail}"
        )
    def _verify_search(
        self,
        goal: str,
        platform: str,
        search_query: str,
        observation_blob: str,
    ) -> bool:
        if mechanical_search_achieved(platform, observation_blob, search_query):
            return True
        verify = verify_media_with_llm_retries(
            self._gemma,
            goal=goal,
            media_action="search",
            observation_blob=observation_blob,
            max_attempts=2,
        )
        return bool(verify and verify.achieved)
    def _log(self, platform: str, action: str, step: str) -> None:
        push_activity_line(f"MediaFlow: platform={platform} action={action} step={step}")
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
    def _perceive(self) -> str:
        """list_open_windows + perceive_desktop → observation blob."""
        parts: list[str] = []
        win = self._run_tool("list_open_windows", {}, summary="media windows")
        if win.success:
            parts.append(f"windows: {(win.detail or win.message or '')[:400]}")
        pd = self._run_tool("perceive_desktop", {}, summary="media perceive")
        if pd.success:
            parts.append(pd.message[:500])
            if pd.detail:
                parts.append(pd.detail[:800])
        else:
            parts.append(f"perceive: fail | {pd.message[:200]}")
        self._assistant._db.insert_log("media_flow", "perceive", parts[-1][:300] if parts else "")
        return "\n".join(parts)
    def _run_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        summary: str,
    ) -> AutomationToolResult:
        return self._agent._run_tool_direct(
            tool_name,
            params,
            summary=summary[:200],
            approved=True,
        )
    def _rank(
        self,
        goal: str,
        search_query: str,
        candidates: list[str],
    ) -> MediaRankerResult | None:
        if not candidates:
            return MediaRankerResult(
                pick_name=None,
                confidence=0.0,
                reason="검색 결과 후보를 화면에서 찾지 못했습니다. 항목 이름을 알려주세요.",
            )
        user_body = (
            f"goal: {goal}\n"
            f"search_query: {search_query}\n"
            f"candidates: {json.dumps(candidates, ensure_ascii=False)}\n"
        )
        raw = self._gemma.chat(
            [
                ChatMessage("system", MEDIA_RESULT_RANKER_SYSTEM),
                ChatMessage("user", user_body),
            ],
            purpose=LlmPurpose.COMPUTER_USE,
            lane="computer_use",
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
