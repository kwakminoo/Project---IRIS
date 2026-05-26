"""MediaPlaybackFlow 단위 테스트 (Fake registry + Fake Gemma)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import MagicMock, patch

from iris.ai.gemma_client import ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.assistant.media_completion import MediaExecutionPhase
from iris.assistant.media_playback_flow import (
    MediaPlaybackFlow,
    MediaRankerResult,
    _PERCEIVE_LOAD_MAX_RETRIES,
    candidates_ready_for_rank,
    code_verify_play,
    code_verify_search,
    derive_success_criteria,
    extract_result_candidates,
    filter_media_candidates,
    filter_video_title_candidates,
    mechanical_pick_candidate,
    parse_media_ranker_json,
    resolve_focus_window_after_open,
    resolve_media_target,
    resolve_ranker_pick,
    should_run_media_flow,
)
from iris.assistant.media_verify import (
    media_play_complete,
    media_pre_rank_ready,
    media_search_complete,
)
from iris.automation.action_executor import ActionExecutor
from iris.automation.media_urls import (
    build_media_open_url,
    build_spotify_search_url,
)
from iris.automation.tool_types import AutomationToolResult
from iris.automation.window_controller import WindowInfo
from iris.monitoring.browser_tab_monitor import BrowserTabMonitor
from iris.storage.database import Database


_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class _MediaGemma:
    """Ranker / Verify 전용 응답 큐."""

    def __init__(self, ranker: str | None = None, verify: str | None = None) -> None:
        self._ranker = ranker
        self._verify = verify
        self.calls: list[Sequence[ChatMessage]] = []
        self.vision_calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        sys = messages[0].content if messages else ""
        if "Media Result Ranker" in sys:
            return self._ranker or '{"pick_name": null, "confidence": 0, "reason": "없음"}'
        if "Media Playback Verifier" in sys:
            return self._verify or '{"achieved": true, "evidence": "ok", "missing": ""}'
        return '{"achieved": false, "evidence": "", "missing": ""}'

    def chat_with_images(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: object,
    ) -> tuple[str, bool]:
        self.vision_calls.append(list(messages))
        sys = messages[0].content if messages else ""
        if "Media Result Ranker" in sys:
            return (
                self._ranker or '{"pick_name": null, "confidence": 0, "reason": "없음"}',
                True,
            )
        if "Media Playback Verifier" in sys:
            return (
                self._verify or '{"achieved": true, "evidence": "ok", "missing": ""}',
                True,
            )
        return ('{"achieved": false, "evidence": "", "missing": ""}', True)


def _youtube_window() -> WindowInfo:
    return WindowInfo("YouTube - Google Chrome", 0, 0, 1280, 720, 12345)


def _patch_media_windows() -> object:
    return patch.multiple(
        "iris.assistant.media_playback_flow.window_controller",
        list_visible_windows=MagicMock(return_value=[_youtube_window()]),
        get_active_window_title=MagicMock(return_value="YouTube - Google Chrome"),
        focus_window_by_hwnd=MagicMock(return_value=True),
    )


def _focus_ok() -> AutomationToolResult:
    return AutomationToolResult(True, "포커스 완료", "ok")


def _perceive_search_ok(url: str) -> AutomationToolResult:
    return AutomationToolResult(
        True,
        f"perceive: ocr | YouTube | {url}",
        json.dumps(
            {
                "perception_source": "ocr",
                "active_window": "YouTube - Google Chrome",
                "summary": f"results search_query=아이유 {url[:60]}",
            },
            ensure_ascii=False,
        ),
    )


def _perceive_play_candidates() -> AutomationToolResult:
    uia = json.dumps(
        {
            "window": "YouTube - Chrome",
            "elements": [
                {"name": "아이유 - 라일락", "type": "Hyperlink"},
                {"name": "다른 가수 - 다른 곡", "type": "Hyperlink"},
            ],
        },
        ensure_ascii=False,
    )
    return AutomationToolResult(
        True,
        "perceive: hybrid | YouTube | results",
        json.dumps(
            {
                "perception_source": "hybrid",
                "active_window": "YouTube - Google Chrome",
                "summary": uia,
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
                "active_window": "YouTube - Google Chrome",
                "summary": "https://www.youtube.com/watch?v=abc123 playing",
            },
            ensure_ascii=False,
        ),
    )


def _media_flow_settings(**overrides: object) -> SimpleNamespace:
    """Ranker·verify 비전 테스트용 최소 Settings."""
    base = {
        "media_ranker_use_screenshot": True,
        "media_ranker_vision_model": "gemma4:26b",
        "gemma_model_name": "gemma4:e2b",
        "gemma_backend": "ollama",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_assistant(
    tmp_path: Path,
    gemma: object,
    *,
    settings: object | None = None,
) -> IrisAssistant:
    db = Database(path=tmp_path / "media_flow.db")
    executor = ActionExecutor(db, {})
    return IrisAssistant(db, executor, gemma, {}, settings=settings)  # type: ignore[arg-type]


def test_should_run_media_flow() -> None:
    assert should_run_media_flow(
        {"media_action": "search", "search_query": "아이유", "platform_hint": "youtube"}
    )
    assert not should_run_media_flow({"media_action": "play"})
    assert not should_run_media_flow({})


def test_derive_success_criteria() -> None:
    assert derive_success_criteria({"media_action": "play"}) == "playback_confirmed"
    assert derive_success_criteria({"media_action": "search"}) == "search_results_visible"
    assert (
        derive_success_criteria(
            {"media_action": "play", "success_criteria": "play_confirmed"}
        )
        == "playback_confirmed"
    )


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


def test_media_pre_rank_ready_rejects_url_only_empty_candidates() -> None:
    url = "https://www.youtube.com/results?search_query=아이유"
    blob = json.dumps(
        {"active_window": "YouTube", "summary": url},
        ensure_ascii=False,
    )
    assert not media_pre_rank_ready("youtube", "아이유", blob, [])
    assert not candidates_ready_for_rank("youtube", "아이유", blob, [])


def test_media_pre_rank_ready_accepts_candidates_and_platform() -> None:
    uia = json.dumps(
        {
            "active_window": "YouTube - Chrome",
            "elements": [
                {"name": "아이유 - 라일락", "type": "Hyperlink"},
                {"name": "다른 곡", "type": "Hyperlink"},
            ],
        },
        ensure_ascii=False,
    )
    assert media_pre_rank_ready(
        "youtube",
        "아이유",
        uia,
        ["아이유 - 라일락"],
    )


def test_media_search_complete_rejects_url_only() -> None:
    url = "https://www.youtube.com/results?search_query=아이유"
    blob = json.dumps(
        {"active_window": "YouTube", "summary": url},
        ensure_ascii=False,
    )
    assert not media_search_complete("youtube", "아이유", blob)


def test_media_search_complete_with_results_ui() -> None:
    uia = json.dumps(
        {
            "active_window": "YouTube - Chrome",
            "elements": [
                {"name": "아이유 - 라일락", "type": "Hyperlink"},
                {"name": "다른 곡", "type": "Hyperlink"},
            ],
        },
        ensure_ascii=False,
    )
    assert media_search_complete("youtube", "아이유", uia)


def test_media_play_complete_rejects_search_url_only() -> None:
    url = "https://www.youtube.com/results?search_query=아이유"
    assert not media_play_complete("youtube", url)


def test_resolve_focus_window_after_open() -> None:
    url = build_media_open_url("youtube", "아이유")
    with patch(
        "iris.assistant.media_playback_flow.window_controller.list_visible_windows",
        return_value=[_youtube_window()],
    ):
        resolved = resolve_focus_window_after_open(
            "youtube",
            open_url=url,
            window_list_blob="YouTube - Google Chrome",
        )
    assert resolved is not None
    assert "YouTube" in resolved.title_sub
    assert resolved.match_reason


def test_media_flow_youtube_search_complete(tmp_path: Path) -> None:
    search_url = build_media_open_url("youtube", "아이유")
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    with _patch_media_windows():
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                _focus_ok(),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
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
        {
            "pick_index": 0,
            "pick_name": "아이유 - 라일락",
            "confidence": 0.9,
            "reason": "제목 일치",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    with _patch_media_windows():
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
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
    perceive_calls = [
        c for c in registry.run.call_args_list if c[0][0] == "perceive_desktop"
    ]
    assert perceive_calls[0][0][1].params.get("window_title_sub") == "YouTube"


def test_play_perceive_loop_has_no_intentional_sleep(tmp_path: Path) -> None:
    """play 경로 전체에서 time.sleep 미호출 — 2번째 perceive에서 PRE_RANK 통과."""
    search_url = build_media_open_url("youtube", "아이유")
    ranker_json = json.dumps(
        {
            "pick_index": 0,
            "pick_name": "아이유 - 라일락",
            "confidence": 0.9,
            "reason": "제목 일치",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    pre_rank_pass = {"n": 0}

    def _criteria_side_effect(
        criteria: object,
        phase: object,
        **kwargs: object,
    ) -> bool:
        ph = phase.value if isinstance(phase, MediaExecutionPhase) else str(phase)
        if ph == MediaExecutionPhase.PRE_RANK.value:
            pre_rank_pass["n"] += 1
            return pre_rank_pass["n"] >= 2
        if ph == MediaExecutionPhase.PLAY_DONE.value:
            return True
        return False

    with (
        _patch_media_windows(),
        patch("time.sleep") as mock_sleep,
        patch(
            "iris.assistant.media_playback_flow.criteria_satisfied",
            side_effect=_criteria_side_effect,
        ),
    ):
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_watch(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "유튜브에서 아이유 틀어줘",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유",
            },
        )
        mock_sleep.assert_not_called()
    assert "재생" in msg
    assert pre_rank_pass["n"] >= 2


def test_perceive_for_play_retries_without_sleep(tmp_path: Path) -> None:
    """_perceive_for_play — 첫 PRE_RANK fail, 둘째 pass, sleep 없음."""
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    pre_rank_pass = {"n": 0}

    def _criteria_side_effect(
        criteria: object,
        phase: object,
        **kwargs: object,
    ) -> bool:
        ph = phase.value if isinstance(phase, MediaExecutionPhase) else str(phase)
        if ph == MediaExecutionPhase.PRE_RANK.value:
            pre_rank_pass["n"] += 1
            return pre_rank_pass["n"] >= 2
        return False

    with (
        _patch_media_windows(),
        patch("time.sleep") as mock_sleep,
        patch(
            "iris.assistant.media_playback_flow.criteria_satisfied",
            side_effect=_criteria_side_effect,
        ),
    ):
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        obs, candidates, ready = flow._perceive_for_play(
            "youtube",
            "아이유",
            open_url=build_media_open_url("youtube", "아이유"),
        )
        mock_sleep.assert_not_called()
    assert ready is True
    assert len(candidates) >= 1
    assert pre_rank_pass["n"] == 2


def test_parse_media_ranker_json() -> None:
    raw = (
        '{"pick_index": 0, "pick_name": "치챗", "confidence": 0.8, "reason": "STT 표기 유지"}'
    )
    parsed = parse_media_ranker_json(raw)
    assert parsed is not None
    assert parsed.pick_name == "치챗"
    assert parsed.pick_index == 0


def test_extract_candidates_from_uia_json() -> None:
    uia = json.dumps(
        {
            "window": "YouTube - Chrome",
            "elements": [
                {"name": "Home", "type": "Button"},
                {"name": "새벽과 반딧불이 - 황인욱", "type": "Hyperlink"},
                {"name": "새벽의 반딧불이 MV", "type": "Text"},
                {"name": "Search", "type": "Edit"},
            ],
        },
        ensure_ascii=False,
    )
    detail = json.dumps(
        {"perception_source": "uia", "active_window": "YouTube", "summary": uia},
        ensure_ascii=False,
    )
    blob = f"perceive: uia | YouTube | ...\n{detail}"
    names = extract_result_candidates(blob, max_items=5)
    assert "새벽과 반딧불이 - 황인욱" in names
    assert "Home" not in names
    assert len(names) <= 5


def test_resolve_ranker_pick_by_index_and_fuzzy() -> None:
    candidates = ["아이유 - 라일락", "다른 가수 - 다른 곡"]
    by_idx = MediaRankerResult(
        pick_name="아이유 - 라일락", pick_index=0, confidence=0.9, reason="ok"
    )
    assert resolve_ranker_pick(by_idx, candidates) == "아이유 - 라일락"
    fuzzy = MediaRankerResult(
        pick_name="아이유 라일락", pick_index=None, confidence=0.85, reason="제목 유사"
    )
    assert resolve_ranker_pick(fuzzy, candidates) == "아이유 - 라일락"


def test_resolve_media_target() -> None:
    yt = resolve_media_target("youtube")
    assert yt.window_title_sub == "YouTube"
    assert yt.url_domain_hint == "youtube.com"
    br = resolve_media_target("browser")
    assert br.window_title_sub == "Chrome"
    assert "Firefox" in br.alt_title_subs


def test_filter_media_candidates_removes_junk() -> None:
    raw = [
        "아이유 - 라일락",
        "Sponsored · 다른 광고",
        "Shorts #shorts 클립",
        "Cursor - IRIS",
        "브라우저",
        "화면 캡처 실패",
    ]
    filtered = filter_media_candidates(
        raw, platform="youtube", search_query="아이유 라일락"
    )
    assert filtered == ["아이유 - 라일락"]


def test_filter_play_pre_rank_keeps_stt_typo_candidates() -> None:
    raw = ["치챗 - 공식 MV", "다른 곡"]
    filtered = filter_media_candidates(
        raw,
        platform="youtube",
        search_query="치챗",
        require_query_token_overlap=False,
    )
    assert "치챗 - 공식 MV" in filtered


def test_candidates_ready_for_rank_rejects_iris_noise() -> None:
    blob = (
        "perceive: uia | Iris | ...\n"
        '{"active_window":"Iris","summary":"Cursor agent"}'
    )
    junk = ["브라우저", "Cursor", "화면 캡처 실패"]
    assert not candidates_ready_for_rank("youtube", "아이유", blob, junk)


def test_perceive_desktop_receives_resolved_window_hint(tmp_path: Path) -> None:
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    with _patch_media_windows():
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        flow._perceive("youtube", open_url=build_media_open_url("youtube", "아이유"))
    perceive_calls = [
        c for c in registry.run.call_args_list if c[0][0] == "perceive_desktop"
    ]
    assert len(perceive_calls) == 1
    params = perceive_calls[0][0][1].params
    assert params.get("focus_hint") == "YouTube"
    assert params.get("window_title_sub") == "YouTube"


def test_media_pre_rank_passes_url_only_with_filtered_candidates() -> None:
    url = "https://www.youtube.com/results?search_query=치챗"
    blob = (
        f"perceive: ocr | YouTube | {url}\n"
        + json.dumps(
            {"active_window": "YouTube - Chrome", "summary": url},
            ensure_ascii=False,
        )
    )
    assert media_pre_rank_ready("youtube", "치챗", blob, ["치챗 - 공식 MV"])


def test_perceive_play_normalizes_active_window_from_resolved(tmp_path: Path) -> None:
    """resolved YouTube + perceive detail에 Iris active_window → 정규화 후 게이트 pass."""
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    iris_detail = json.dumps(
        {
            "perception_source": "uia",
            "active_window": "Iris",
            "summary": json.dumps(
                {
                    "elements": [
                        {"name": "치챗 - 공식 MV", "type": "Hyperlink"},
                        {"name": "다른 곡", "type": "Hyperlink"},
                    ],
                },
                ensure_ascii=False,
            ),
        },
        ensure_ascii=False,
    )
    with _patch_media_windows():
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                AutomationToolResult(
                    True,
                    "perceive: uia | Iris",
                    iris_detail,
                ),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        blob = flow._perceive(
            "youtube",
            open_url=build_media_open_url("youtube", "치챗"),
            for_play=True,
        )
    assert '"active_window": "YouTube"' in blob or '"active_window":"YouTube"' in blob
    raw = extract_result_candidates(blob)
    candidates = filter_video_title_candidates(
        filter_media_candidates(
            raw, platform="youtube", search_query="치챗", require_query_token_overlap=False
        ),
        platform="youtube",
        search_query="치챗",
    )
    assert media_pre_rank_ready("youtube", "치챗", blob, candidates)


def test_play_perceive_skips_full_screen_ocr(tmp_path: Path) -> None:
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    with (
        _patch_media_windows(),
        patch(
            "iris.automation.tools.read_screen_summary_text",
            side_effect=AssertionError("full screen OCR must not run on play perceive"),
        ),
    ):
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                AutomationToolResult(
                    True,
                    "perceive: uia | YouTube",
                    json.dumps(
                        {
                            "perception_source": "uia",
                            "active_window": "YouTube",
                            "summary": "",
                        },
                        ensure_ascii=False,
                    ),
                ),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        flow._perceive("youtube", open_url=build_media_open_url("youtube", "아이유"), for_play=True)
    params = [
        c[0][1].params
        for c in registry.run.call_args_list
        if c[0][0] == "perceive_desktop"
    ][0]
    assert params.get("prefer_window_only") is True


def test_play_degraded_path_rank_click_when_gate_fail_has_candidates(
    tmp_path: Path,
) -> None:
    """PRE_RANK fail + 후보≥1 → Ranker·uia_click (gate_fail 질문 없음)."""
    search_url = build_media_open_url("youtube", "치챗")
    ranker_json = json.dumps(
        {
            "pick_index": 0,
            "pick_name": "치챗 - 공식 MV",
            "confidence": 0.85,
            "reason": "제목 일치",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry

    def _gate_fail_but_candidates() -> AutomationToolResult:
        uia = json.dumps(
            {
                "window": "YouTube - Chrome",
                "elements": [
                    {"name": "치챗 - 공식 MV", "type": "Hyperlink"},
                ],
            },
            ensure_ascii=False,
        )
        return AutomationToolResult(
            True,
            "perceive: uia | Iris | results",
            json.dumps(
                {
                    "perception_source": "uia",
                    "active_window": "Iris",
                    "summary": uia,
                },
                ensure_ascii=False,
            ),
        )

    with (
        patch(
            "iris.assistant.media_playback_flow.window_controller.list_visible_windows",
            return_value=[_youtube_window()],
        ),
        patch(
            "iris.assistant.media_playback_flow.window_controller.get_active_window_title",
            return_value="Iris",
        ),
        patch.object(MediaPlaybackFlow, "_focus_resolved_window"),
        patch.object(MediaPlaybackFlow, "_focus_media_target"),
        patch(
            "iris.assistant.media_verify.media_pre_rank_ready",
            return_value=False,
        ),
    ):
        effects: list[AutomationToolResult] = [
            AutomationToolResult(True, "URL 열림", search_url[:80]),
        ]
        for _ in range(_PERCEIVE_LOAD_MAX_RETRIES):
            effects.extend(
                [
                    AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                    _gate_fail_but_candidates(),
                ]
            )
        effects.extend(
            [
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_watch(),
            ]
        )
        registry.run = MagicMock(side_effect=effects)  # type: ignore[method-assign]
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "유튜브에서 치챗 틀어줘",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "치챗",
            },
        )
    assert "USER_QUESTION" not in msg or "검색 결과가 아직" not in msg
    assert "재생" in msg
    click_calls = [c for c in registry.run.call_args_list if c[0][0] == "uia_click"]
    assert len(click_calls) >= 1
    ranker_calls = [c for c in gemma.calls if "Media Result Ranker" in c[0].content]
    assert len(ranker_calls) == 1


def test_play_asks_user_when_gate_never_passes(tmp_path: Path) -> None:
    search_url = build_media_open_url("youtube", "아이유")
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry

    def _iris_noise_perceive() -> AutomationToolResult:
        return AutomationToolResult(
            True,
            "perceive: uia | Iris | noise",
            json.dumps(
                {
                    "perception_source": "uia",
                    "active_window": "Iris",
                    "summary": "브라우저\nCursor\n화면 캡처 실패",
                },
                ensure_ascii=False,
            ),
        )

    with (
        patch(
            "iris.assistant.media_playback_flow.window_controller.list_visible_windows",
            return_value=[WindowInfo("Iris", 0, 0, 800, 600, 99)],
        ),
        patch(
            "iris.assistant.media_playback_flow.window_controller.get_active_window_title",
            return_value="Iris",
        ),
        patch.object(MediaPlaybackFlow, "_focus_media_target"),
        patch.object(MediaPlaybackFlow, "_focus_resolved_window"),
    ):
        effects: list[AutomationToolResult] = [
            AutomationToolResult(True, "URL 열림", search_url[:80]),
        ]
        for _ in range(4):
            effects.extend(
                [
                    AutomationToolResult(True, "창", "Iris"),
                    _iris_noise_perceive(),
                ]
            )
        registry.run = MagicMock(side_effect=effects)  # type: ignore[method-assign]
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "유튜브에서 아이유 틀어줘",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유",
            },
        )
    assert msg.startswith("USER_QUESTION:")
    assert "검색 결과" in msg
    ranker_calls = [c for c in gemma.calls if "Media Result Ranker" in c[0].content]
    assert len(ranker_calls) == 0


def test_filter_video_title_candidates_excludes_chrome_ui() -> None:
    raw = [
        "Home",
        "Search",
        "로그인",
        "Subscribe",
        "1234567",
        "!!!@@@###",
        "조회수 12만회",
        "YouTube",
        "Mix · playlist",
        "알레프 칫챗 - Official MV",
    ]
    out = filter_video_title_candidates(
        raw, platform="youtube", search_query="알레프 칫챗"
    )
    assert out == ["알레프 칫챗 - Official MV"]


def test_filter_video_title_candidates_keeps_hyperlink_titles() -> None:
    uia = json.dumps(
        {
            "window": "YouTube - Chrome",
            "elements": [
                {"name": "Home", "type": "Button"},
                {"name": "새벽과 반딧불이 - 황인욱", "type": "Hyperlink"},
                {"name": "Search", "type": "Edit"},
            ],
        },
        ensure_ascii=False,
    )
    detail = json.dumps(
        {"perception_source": "uia", "active_window": "YouTube", "summary": uia},
        ensure_ascii=False,
    )
    blob = f"perceive: uia | YouTube | ...\n{detail}"
    names = extract_result_candidates(blob, max_items=5)
    filtered = filter_video_title_candidates(
        filter_media_candidates(
            names,
            platform="youtube",
            search_query="새벽 반딧불이",
            require_query_token_overlap=False,
        ),
        platform="youtube",
        search_query="새벽 반딧불이",
    )
    assert "새벽과 반딧불이 - 황인욱" in filtered
    assert "Home" not in filtered
    assert "Search" not in filtered


def test_mechanical_pick_candidate_prefers_overlap() -> None:
    candidates = ["다른 곡 - B", "알레프 칫챗 - Official MV", "무관한 제목"]
    pick = mechanical_pick_candidate(candidates, "알레프 칫챗")
    assert pick == "알레프 칫챗 - Official MV"


def test_mechanical_pick_candidate_zero_overlap_uses_first() -> None:
    candidates = ["첫 번째 영상 제목", "두 번째 영상 제목"]
    pick = mechanical_pick_candidate(candidates, "완전다른검색어")
    assert pick == "첫 번째 영상 제목"


def test_play_rank_null_uses_mechanical_fallback(tmp_path: Path) -> None:
    """Ranker null이어도 후보≥1이면 uia_click·재생 완료."""
    search_url = build_media_open_url("youtube", "알레프 칫챗")
    ranker_json = json.dumps(
        {
            "pick_index": None,
            "pick_name": None,
            "confidence": 0.0,
            "reason": "후보 목록에 없음",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    with (
        _patch_media_windows(),
        patch.object(
            MediaPlaybackFlow, "_capture_play_verify_screenshot", return_value=None
        ),
    ):
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_watch(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "알레프 칫챗 틀어줘",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "알레프 칫챗",
            },
        )
    assert "재생" in msg
    click_calls = [c for c in registry.run.call_args_list if c[0][0] == "uia_click"]
    assert len(click_calls) >= 1
    rows = assistant._db._execute(
        "SELECT message, result FROM logs WHERE type=? AND message=?",
        ("media_flow", "rank_fallback"),
    ).fetchall()
    assert len(rows) >= 1


def test_play_logs_rank_input(tmp_path: Path) -> None:
    search_url = build_media_open_url("youtube", "아이유")
    ranker_json = json.dumps(
        {
            "pick_index": 0,
            "pick_name": "아이유 - 라일락",
            "confidence": 0.9,
            "reason": "ok",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    with (
        _patch_media_windows(),
        patch.object(
            MediaPlaybackFlow, "_capture_play_verify_screenshot", return_value=None
        ),
    ):
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_watch(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        flow.run(
            "아이유 라일락",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유 라일락",
            },
        )
    rows = assistant._db._execute(
        "SELECT message, result FROM logs WHERE type=? AND message=?",
        ("media_flow", "rank_input"),
    ).fetchall()
    assert len(rows) >= 1
    payload = (rows[0]["result"] or rows[0]["message"] or "")
    assert "아이유" in payload


def test_rank_uses_chat_with_images_when_screenshot(tmp_path: Path) -> None:
    """Ranker — 스크린샷 있으면 chat_with_images·rank_vision used=True."""
    ranker_json = json.dumps(
        {
            "pick_index": 0,
            "pick_name": "아이유 - 라일락",
            "confidence": 0.9,
            "reason": "비전",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    settings = _media_flow_settings()
    assistant = _make_assistant(tmp_path, gemma, settings=settings)
    registry = assistant._executor.tool_registry
    search_url = build_media_open_url("youtube", "아이유")
    with (
        _patch_media_windows(),
        patch.object(
            MediaPlaybackFlow,
            "_capture_play_verify_screenshot",
            return_value=_FAKE_PNG,
        ),
    ):
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_watch(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "아이유 라일락",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유 라일락",
            },
        )
    assert "재생" in msg
    assert len(gemma.vision_calls) >= 1
    ranker_msgs = gemma.vision_calls[0]
    user_msg = ranker_msgs[1]
    assert user_msg.images and len(user_msg.images) == 1
    rows = assistant._db._execute(
        "SELECT result FROM logs WHERE type=? AND message=?",
        ("media_flow", "rank_vision"),
    ).fetchall()
    assert any("used=True" in (r["result"] or "") for r in rows)


def test_rank_text_fallback_logs_when_no_screenshot(tmp_path: Path) -> None:
    """스크린샷 없을 때 text-only·rank_vision used=false 로그."""
    ranker_json = json.dumps(
        {
            "pick_index": 0,
            "pick_name": "아이유 - 라일락",
            "confidence": 0.9,
            "reason": "텍스트",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    settings = _media_flow_settings()
    assistant = _make_assistant(tmp_path, gemma, settings=settings)
    registry = assistant._executor.tool_registry
    search_url = build_media_open_url("youtube", "아이유")
    with (
        _patch_media_windows(),
        patch.object(
            MediaPlaybackFlow,
            "_capture_play_verify_screenshot",
            return_value=None,
        ),
    ):
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_watch(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        flow.run(
            "아이유",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유",
            },
        )
    assert len(gemma.vision_calls) == 0
    assert len(gemma.calls) >= 1
    rows = assistant._db._execute(
        "SELECT result FROM logs WHERE type=? AND message=?",
        ("media_flow", "rank_vision"),
    ).fetchall()
    assert any(
        "screenshot_capture_failed" in (r["result"] or "") for r in rows
    )


def test_play_verify_logs_verify_play_with_vision(tmp_path: Path) -> None:
    """기계 play 실패 후 LLM verify — verify_play·vision_used 로그."""
    ranker_json = json.dumps(
        {
            "pick_index": 0,
            "pick_name": "아이유 - 라일락",
            "confidence": 0.9,
            "reason": "ok",
        },
        ensure_ascii=False,
    )
    verify_json = json.dumps(
        {"achieved": True, "evidence": "watch 화면", "missing": ""},
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json, verify=verify_json)
    settings = _media_flow_settings()
    assistant = _make_assistant(tmp_path, gemma, settings=settings)
    registry = assistant._executor.tool_registry
    search_url = build_media_open_url("youtube", "아이유")

    from iris.assistant import media_playback_flow as mpf

    _orig_criteria = mpf.criteria_satisfied

    def _criteria_side_effect(
        criteria: object,
        phase: object,
        **kwargs: object,
    ) -> bool:
        ph = phase.value if isinstance(phase, MediaExecutionPhase) else str(phase)
        if ph == MediaExecutionPhase.PLAY_DONE.value:
            return False
        return _orig_criteria(criteria, phase, **kwargs)

    with (
        _patch_media_windows(),
        patch.object(
            MediaPlaybackFlow,
            "_capture_play_verify_screenshot",
            return_value=_FAKE_PNG,
        ),
        patch(
            "iris.assistant.media_playback_flow.criteria_satisfied",
            side_effect=_criteria_side_effect,
        ),
    ):
        _win = AutomationToolResult(True, "창", "YouTube - Google Chrome")
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                _win,
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                _win,
                _perceive_play_candidates(),
                _win,
                _perceive_play_candidates(),
                _win,
                _perceive_play_candidates(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "아이유",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유",
            },
        )
    assert "재생" in msg
    verify_vision = [
        c
        for c in gemma.vision_calls
        if c and "Media Playback Verifier" in c[0].content
    ]
    assert len(verify_vision) >= 1
    assert verify_vision[0][1].images
    rows = assistant._db._execute(
        "SELECT result FROM logs WHERE type=? AND message=?",
        ("media_flow", "verify_play"),
    ).fetchall()
    assert len(rows) >= 1
    payload = rows[0]["result"] or ""
    assert "vision_used" in payload
    assert "true" in payload.lower()


def test_youtube_dom_play_open_url_twice(tmp_path: Path) -> None:
    """DOM mock: search open_url + watch open_url, uia_click 없음."""
    search_url = build_media_open_url("youtube", "아이유 라일락")
    watch_url = "https://www.youtube.com/watch?v=abc111"
    gemma = _MediaGemma()
    assistant = _make_assistant(tmp_path, gemma)
    monitor = BrowserTabMonitor()
    monitor.ingest(
        1,
        "아이유 - YouTube",
        search_url,
        "results",
        youtube_search_results=[
            ("아이유 - 라일락 MV", watch_url),
            ("다른 곡", "https://www.youtube.com/watch?v=other"),
        ],
    )
    assistant._browser_monitor = monitor  # noqa: SLF001
    registry = assistant._executor.tool_registry
    with _patch_media_windows():
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "URL 열림", watch_url[:80]),
                _focus_ok(),
                _perceive_play_watch(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "유튜브에서 아이유 라일락 틀어줘",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유 라일락",
            },
        )
    assert "재생" in msg
    open_calls = [c for c in registry.run.call_args_list if c[0][0] == "open_url"]
    assert len(open_calls) == 2
    assert "search_query=" in str(open_calls[0][0][1].params.get("url", ""))
    assert open_calls[1][0][1].params.get("url") == watch_url
    assert not any(c[0][0] == "uia_click" for c in registry.run.call_args_list)
    yt_logs = assistant._db._execute(
        "SELECT message, result FROM logs WHERE type=?",
        ("youtube_dom",),
    ).fetchall()
    assert any("picked" in str(r["message"]) for r in yt_logs)


def test_youtube_dom_empty_falls_back_to_legacy_play(tmp_path: Path) -> None:
    """DOM empty → 기존 rank·click 경로."""
    search_url = build_media_open_url("youtube", "아이유")
    ranker_json = json.dumps(
        {
            "pick_index": 0,
            "pick_name": "아이유 - 라일락",
            "confidence": 0.9,
            "reason": "일치",
        },
        ensure_ascii=False,
    )
    gemma = _MediaGemma(ranker=ranker_json)
    assistant = _make_assistant(tmp_path, gemma)
    assistant._browser_monitor = BrowserTabMonitor()  # noqa: SLF001
    registry = assistant._executor.tool_registry
    with _patch_media_windows():
        registry.run = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                AutomationToolResult(True, "URL 열림", search_url[:80]),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_candidates(),
                AutomationToolResult(True, "UIA 클릭", "ok"),
                AutomationToolResult(True, "창", "YouTube - Google Chrome"),
                _perceive_play_watch(),
            ]
        )
        flow = MediaPlaybackFlow(
            ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        )
        msg = flow.run(
            "아이유 재생",
            {
                "platform_hint": "youtube",
                "media_action": "play",
                "search_query": "아이유",
            },
        )
    assert "재생" in msg
    assert any(c[0][0] == "uia_click" for c in registry.run.call_args_list)
