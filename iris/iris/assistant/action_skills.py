"""앱별 고정 단계 스킬 — PAV 플래너 우회 (MediaPlaybackFlow와 동일 패턴).

메모장 입력·카톡 보내기·디스코드 통화 등은 UIA/전용 API 우선, type_text는 최후.
입력 충돌 도구 사용 전 ComputerUseAgent가 notify + delay를 수행합니다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.assistant.computer_use_agent import ComputerUseAgent


class ActionSkill:
    """Router slots + goal로 매칭되는 결정론적 실행 스킬 (Protocol 호환)."""

    skill_id: str

    def matches(self, goal: str, slots: dict[str, Any]) -> bool:
        raise NotImplementedError

    def run(
        self,
        agent: ComputerUseAgent,
        goal: str,
        slots: dict[str, Any],
    ) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class SkillMatch:
    skill_id: str
    reason: str


# Router task_type → 스킬 후보
_TASK_TYPE_SKILL: dict[str, str] = {
    "compose_text": "text_compose",
    "send_message": "send_message",
    "voip_call": "voip_call",
    "media_play": "media_play",
}

# skill_id → runner (ComputerUseAgent.run()에서 PAV·quick launch 우회)
SKILL_RUNNERS: dict[str, Callable[["ComputerUseAgent", str, dict[str, Any]], str]] = {}


def _register_skill_runners() -> None:
    if SKILL_RUNNERS:
        return
    from iris.assistant.media_playback_flow import MediaPlaybackFlow
    from iris.assistant.send_message_flow import SendMessageFlow
    from iris.assistant.text_compose_flow import TextComposeFlow

    SKILL_RUNNERS["media_play"] = lambda a, g, s: MediaPlaybackFlow(a).run(g, s)
    SKILL_RUNNERS["text_compose"] = lambda a, g, s: TextComposeFlow(a).run(g, s)
    SKILL_RUNNERS["send_message"] = lambda a, g, s: SendMessageFlow(a).run(g, s)


def resolve_skill_id(slots: dict[str, Any]) -> str | None:
    """slots.skill_id 또는 task_type으로 스킬 식별."""
    explicit = str(slots.get("skill_id") or "").strip()
    if explicit:
        return explicit
    task = str(slots.get("task_type") or "").strip().lower()
    return _TASK_TYPE_SKILL.get(task)


def should_dispatch_skill(slots: dict[str, Any] | None) -> bool:
    """스킬 경로 진입 — media_play는 search_query 등 추가 조건."""
    if not slots:
        return False
    sid = resolve_skill_id(slots)
    if not sid:
        return False
    if sid == "media_play":
        from iris.assistant.media_playback_flow import should_run_media_flow

        return should_run_media_flow(slots)
    return sid in {"text_compose", "send_message", "voip_call"}


def run_skill(
    skill_id: str,
    agent: ComputerUseAgent,
    goal: str,
    slots: dict[str, Any],
) -> str:
    """등록된 스킬 runner 실행."""
    _register_skill_runners()
    runner = SKILL_RUNNERS.get(skill_id)
    if runner is None:
        return f"알 수 없는 스킬입니다: {skill_id}"
    return runner(agent, goal, slots)


def clarify_missing_skill_slots(
    task_type: str | None,
    slots: dict[str, Any],
) -> str | None:
    """
    Router 슬롯 검증 — 필수 slots 없으면 clarify 문장 (goal regex 추출 금지).
    """
    task = (task_type or str(slots.get("task_type") or "")).strip().lower()
    sid = resolve_skill_id({**slots, "task_type": task}) if task else resolve_skill_id(slots)

    if sid == "text_compose" or task == "compose_text":
        app_key = str(slots.get("app_key") or "").strip()
        text = str(slots.get("text_to_type") or "").strip()
        if not app_key and not text:
            return "어느 앱에 어떤 내용을 입력할까요?"
        if not app_key:
            return "어느 앱에 입력할까요? (예: 메모장)"
        if not text:
            return "어떤 내용을 입력할까요?"
        return None

    if sid == "send_message" or task == "send_message":
        app_key = str(slots.get("app_key") or "").strip()
        message_text = str(slots.get("message_text") or "").strip()
        if not app_key and not message_text:
            return "어느 앱으로 어떤 메시지를 보낼까요?"
        if not app_key:
            return "어느 앱으로 메시지를 보낼까요? (예: 디스코드, 카카오톡)"
        if not message_text:
            return "어떤 내용을 보낼까요?"
        return None

    return None


def describe_skill_route(goal: str, slots: dict[str, Any]) -> SkillMatch | None:
    """로그·문서용 — 어떤 스킬 경로가 적합한지 설명만 (실행 없음)."""
    sid = resolve_skill_id(slots)
    if not sid:
        return None
    if sid == "text_compose":
        text = str(slots.get("text_to_type") or "").strip()
        if text:
            return SkillMatch(sid, f"앱에 텍스트 입력: {text[:40]}")
        return SkillMatch(sid, "앱에 텍스트 입력 (slots.text_to_type 필요)")
    if sid == "send_message":
        return SkillMatch(sid, "메시지 전송 (UIA·단축키 우선, type_text 최후)")
    if sid == "voip_call":
        return SkillMatch(sid, "통화/음성 연결 (UIA 버튼·단축키)")
    return SkillMatch(sid, f"goal={goal[:60]}")
