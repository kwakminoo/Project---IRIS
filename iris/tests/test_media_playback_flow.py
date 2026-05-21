"""MediaPlaybackFlow 단위 테스트 (Fake registry + Fake Gemma)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence
from unittest.mock import MagicMock

from iris.ai.gemma_client import ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.assistant.media_playback_flow import (
    MediaPlaybackFlow,
    code_verify_play,
    code_verify_search,
    parse_media_ranker_json,
    should_run_media_flow,
)
from iris.automation.action_executor import ActionExecutor
from iris.automation.media_urls import (
    build_media_open_url,
    build_spotify_search_url,
)
from iris.automation.tool_types import AutomationToolResult
from iris.storage.database import Database


class _MediaGemma:
    """Ranker / Verify 전용 응답 큐."""

    def __init__(self, ranker: str | None = None, verify: str | None = None) -> None:
        self._ranker = ranker
        self._verify = verify
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        sys = messages[0].content if messages else ""
        if "Media Result Ranker" in sys:
            return self._ranker or '{"pick_name": null, "confidence": 0, "reason": "없음"}'
        if "Media Playback Verifier" in sys:
            return self._verify or '{"achieved": true, "evidence": "ok", "missing": ""}'
        return '{"achieved": false, "evidence": "", "missing": ""}'


def _perceive_search_ok(url: str) -> AutomationToolResult:
    return AutomationToolResult(
        True,
        f"perceive: ocr | YouTube | {url}",
        json.dumps(
            {
                "perception_source": "ocr",
                "active_window": "YouTube",
                "summary": f"results search_query=아이유 {url[:60]}",
            },
            ensure_ascii=False,
        ),
    )


def _perceive_play_candidates() -> AutomationToolResult:
    return AutomationToolResult(
        True,
        "perceive: hybrid | YouTube | results",
        json.dumps(
            {
                "perception_source": "hybrid",
                "active_window": "YouTube",
                "summary": "아이유 - 라일락\n다른 가수 - 다른 곡",
            },
            ensure_ascii=False,
        ),
    )


def _perceive_play_watch() -> AutomationToolResult:
    return AutomationToolResult(
        True,
        "perceive: ocr | YouTube | watch",
        json.dumps(
            {
                "perception_source": "ocr",
                "active_window": "YouTube",
                "summary": "https://www.youtube.com/watch?v=abc123 playing",
            },
            ensure_ascii=False,
        ),
    )


def _make_assistant(tmp_path: Path, gemma: object) -> IrisAssistant:
    db = Database(path=tmp_path / "media_flow.db")
    executor = ActionExecutor(db, {})
    return IrisAssistant(db, executor, gemma, {})  # type: ignore[arg-type]


def test_should_run_media_flow() -> None:
    assert should_run_media_flow(
        {"media_action": "search", "search_query": "아이유", "platform_hint": "youtube"}
    )
    assert not should_run_media_flow({"media_action": "play"})
    assert not should_run_media_flow({})


def test_build_media_open_url_spotify() -> None:
    url = build_spotify_search_url("뉴진스")
    assert "open.spotify.com/search" in url
    assert build_media_open_url("spotify", "뉴진스") == url


def test_code_verify_gates() -> None:
    assert code_verify_search(
        "youtube",
        "https://www.youtube.com/results?search_query=아이유",
        "아이유",
    )
    assert code_verify_play("youtube", "https://www.youtube.com/watch?v=x")


def test_media_flow_youtube_search_complete(tmp_path: Path) -> None:
    search_url = build_media_open_url("youtube", "아이유")
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "URL 열림", search_url[:80]),
            AutomationToolResult(True, "창", "Chrome"),
            _perceive_search_ok(search_url),
        ]
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    msg = agent.run(
        "유튜브에서 아이유 검색해줘",
        slots={
            "platform_hint": "youtube",
            "media_action": "search",
            "search_query": "아이유",
            "task_type": "media_play",
        },
    )

    assert "검색 결과" in msg
    open_calls = [c for c in registry.run.call_args_list if c[0][0] == "open_url"]
    assert len(open_calls) == 1
    assert "search_query=" in str(open_calls[0][0][1].params.get("url", ""))
    assert not any(
        c and "Computer Use 플래너" in c[0].content for c in gemma.calls
    )


def test_media_flow_youtube_play_rank_click_verify(tmp_path: Path) -> None:
    search_url = build_media_open_url("youtube", "아이유")
    ranker_json = json.dumps(
        {"pick_name": "아이유 - 라일락", "confidence": 0.9, "reason": "제목 일치"},
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "URL 열림", search_url[:80]),
            AutomationToolResult(True, "창", "YouTube"),
            _perceive_play_candidates(),
            AutomationToolResult(True, "UIA 클릭", "ok"),
            AutomationToolResult(True, "창", "YouTube"),
            _perceive_play_watch(),
        ]
    )
    flow = MediaPlaybackFlow(
        ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    )
    msg = flow.run(
        "유튜브에서 아이유 라일락 재생",
        {
            "platform_hint": "youtube",
            "media_action": "play",
            "search_query": "아이유 라일락",
        },
    )

    assert "재생" in msg
    click_calls = [c for c in registry.run.call_args_list if c[0][0] == "uia_click"]
    assert len(click_calls) >= 1
    assert click_calls[0][0][1].params.get("name") == "아이유 - 라일락"
    ranker_calls = [c for c in gemma.calls if "Media Result Ranker" in c[0].content]
    assert len(ranker_calls) == 1


def test_parse_media_ranker_json() -> None:
    raw = '{"pick_name": "치챗", "confidence": 0.8, "reason": "STT 표기 유지"}'
    parsed = parse_media_ranker_json(raw)
    assert parsed is not None
    assert parsed.pick_name == "치챗"
