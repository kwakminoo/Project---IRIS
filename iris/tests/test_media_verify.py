"""media_verify 기계 게이트·CU play step_complete 가드 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.assistant.media_verify import (
    mechanical_play_achieved,
    media_pre_rank_ready,
    play_step_complete_allowed,
)
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.storage.database import Database


def test_mechanical_play_youtube_watch_and_shorts() -> None:
    assert mechanical_play_achieved(
        "youtube", "perceive | https://www.youtube.com/watch?v=abc"
    )
    assert mechanical_play_achieved("youtube", "https://www.youtube.com/shorts/xyz")


def test_media_pre_rank_ready_url_only_with_candidates() -> None:
    """URL+search_query만 있어도 필터 후보≥1이면 Ranker 진입."""
    url = "https://www.youtube.com/results?search_query=치챗"
    blob = json.dumps(
        {"active_window": "YouTube - Chrome", "summary": url},
        ensure_ascii=False,
    )
    assert media_pre_rank_ready("youtube", "치챗", blob, ["치챗 - 공식 MV"])


def test_media_pre_rank_ready_rejects_url_only_no_candidates() -> None:
    url = "https://www.youtube.com/results?search_query=치챗"
    blob = json.dumps(
        {"active_window": "YouTube - Chrome", "summary": url},
        ensure_ascii=False,
    )
    assert not media_pre_rank_ready("youtube", "치챗", blob, [])


def test_media_pre_rank_ready_rejects_iris_active_with_candidates() -> None:
    blob = json.dumps(
        {"active_window": "Iris", "summary": "some results"},
        ensure_ascii=False,
    )
    assert not media_pre_rank_ready(
        "youtube", "아이유", blob, ["아이유 - 라일락"]
    )


def test_mechanical_play_rejects_search_results_only() -> None:
    blob = "https://www.youtube.com/results?search_query=아이유"
    assert not mechanical_play_achieved("youtube", blob)


def test_play_step_complete_allowed_with_watch() -> None:
    slots = {"media_action": "play", "platform_hint": "youtube"}
    obs = [
        "perceive: ocr | YouTube",
        "https://www.youtube.com/watch?v=abc123 playing",
    ]
    ok, msg = play_step_complete_allowed(slots, obs)
    assert ok is True
    assert msg == ""


def test_play_step_complete_rejected_without_watch() -> None:
    slots = {"media_action": "play", "platform_hint": "youtube"}
    obs = [
        "perceive: ocr | YouTube",
        "https://www.youtube.com/results?search_query=아이유",
    ]
    ok, msg = play_step_complete_allowed(slots, obs)
    assert ok is False
    assert "play not confirmed" in msg


class _StepQueueGemma:
    def __init__(self, steps: list[str]) -> None:
        self._steps = list(steps)

    def chat(self, messages, **kwargs: object) -> str:
        if messages and "Computer Use 플래너" in messages[0].content:
            if self._steps:
                return self._steps.pop(0)
            return '{"tool": "step_failed", "params": {}, "reason": "큐 소진"}'
        if messages and "Media Playback Verifier" in messages[0].content:
            return (
                '{"achieved": false, "evidence": "", '
                '"missing": "watch URL 없음"}'
            )
        return "{}"


def _perceive_ok(summary: str) -> AutomationToolResult:
    return AutomationToolResult(
        True,
        f"perceive: ocr | YouTube | {summary}",
        '{"perception_source":"ocr","active_window":"YouTube","summary":"'
        + summary
        + '"}',
    )


def test_cu_step_complete_play_without_watch_rejected(tmp_path: Path) -> None:
    """Media Flow 미진입(play 슬롯·search_query 없음) — 거짓 complete 차단."""
    gemma = _StepQueueGemma(
        [
            '{"tool": "step_complete", "params": {}, "reason": "재생 완료"}',
            '{"tool": "step_complete", "params": {}, "reason": "재생 완료"}',
            '{"tool": "step_complete", "params": {}, "reason": "재생 완료"}',
            '{"tool": "step_complete", "params": {}, "reason": "재생 완료"}',
        ]
    )
    db = Database(path=tmp_path / "play_reject.db")
    assistant = IrisAssistant(db, ActionExecutor(db, {}), gemma, {})  # type: ignore[arg-type]
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "창", "Chrome"),
            _perceive_ok("results search_query=아이유 only"),
        ]
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=8)  # type: ignore[arg-type]
    msg = agent.run(
        "유튜브에서 아이유 틀어줘",
        slots={
            "media_action": "play",
            "platform_hint": "youtube",
            "query": "아이유",
        },
    )
    assert "재생 화면" in msg or "확인하지 못해" in msg or "검증" in msg
    assert msg.strip() != "재생 완료"


def test_cu_step_complete_play_with_watch_allowed(tmp_path: Path) -> None:
    gemma = _StepQueueGemma(
        [
            '{"tool": "step_complete", "params": {}, "reason": "아이유 재생 중"}',
        ]
    )
    db = Database(path=tmp_path / "play_ok.db")
    assistant = IrisAssistant(db, ActionExecutor(db, {}), gemma, {})  # type: ignore[arg-type]
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "창", "Chrome"),
            _perceive_ok("https://www.youtube.com/watch?v=abc playing"),
        ]
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    msg = agent.run(
        "유튜브 재생",
        slots={"media_action": "play", "platform_hint": "youtube", "query": "아이유"},
    )
    assert "재생" in msg or "완료" in msg
