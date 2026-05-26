"""ComputerUseAgent·parse_computer_use_step 테스트."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import MagicMock, patch

import pytest

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.assistant.action_plan import parse_computer_use_step
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.storage.database import Database

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _cu_vlm_settings(**overrides: object) -> SimpleNamespace:
    base = {
        "computer_use_vlm_enabled": True,
        "computer_use_vision_model": "gemma4:26b",
        "gemma_model_name": "gemma4:e2b",
        "gemma_backend": "ollama",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _StepQueueGemma:
    """Computer Use 플래너 호출마다 큐에서 JSON 스텝을 반환."""

    def __init__(self, steps: list[str]) -> None:
        self._steps = list(steps)
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        if messages and "Computer Use 플래너" in messages[0].content:
            if self._steps:
                return self._steps.pop(0)
            return '{"tool": "step_failed", "params": {}, "reason": "큐 소진"}'
        return "unused"


class _RepeatGemma:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        return self._reply


class _VisionStepGemma(_StepQueueGemma):
    """VLM on — chat_with_images 호출 추적."""

    def __init__(self, steps: list[str]) -> None:
        super().__init__(steps)
        self.vision_calls: list[Sequence[ChatMessage]] = []

    def chat_with_images(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: object,
    ) -> tuple[str, bool]:
        self.vision_calls.append(list(messages))
        return self.chat(messages, **kwargs), True


def _make_assistant(
    tmp_path: Path,
    gemma: object,
    *,
    settings: object | None = None,
) -> IrisAssistant:
    db = Database(path=tmp_path / "cu.db")
    executor = ActionExecutor(db, {})
    return IrisAssistant(db, executor, gemma, {}, settings=settings)  # type: ignore[arg-type]


def test_parse_computer_use_step_valid() -> None:
    raw = '{"tool": "launch_app", "params": {"app_key": "discord"}, "reason": "디스코드 실행"}'
    step = parse_computer_use_step(raw)
    assert step is not None
    assert step.tool == "launch_app"
    assert step.params["app_key"] == "discord"
    assert step.reason == "디스코드 실행"


def test_parse_computer_use_step_rejects_unknown() -> None:
    assert parse_computer_use_step('{"tool": "bogus", "params": {}}') is None


def _perceive_ok() -> AutomationToolResult:
    return AutomationToolResult(
        True,
        "perceive: ocr | Notepad | hello",
        '{"perception_source":"ocr","active_window":"Notepad","summary":"hello"}',
    )


def test_two_step_launch_complete(tmp_path: Path) -> None:
    gemma = _StepQueueGemma(
        [
            '{"tool": "launch_app", "params": {"app_key": "discord", "display_name": "Discord"}, "reason": "실행"}',
            '{"tool": "step_complete", "params": {}, "reason": "디스코드를 실행했습니다."}',
        ]
    )
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry

    mock_run = MagicMock(
        side_effect=[
            AutomationToolResult(True, "창 목록", "Cursor"),
            _perceive_ok(),
            AutomationToolResult(True, "Discord 실행됨", "ok"),
            AutomationToolResult(True, "창 목록", "Discord"),
            _perceive_ok(),
        ]
    )
    registry.run = mock_run  # type: ignore[method-assign]

    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=10)  # type: ignore[arg-type]
    msg = agent.run("디스코드 실행해줘")

    assert "디스코드" in msg or "완료" in msg
    assert mock_run.call_count >= 5
    planner_calls = [c for c in gemma.calls if c and "Computer Use 플래너" in c[0].content]
    assert len(planner_calls) == 2


def test_step_complete_without_perceive_rejected(tmp_path: Path) -> None:
    gemma = _StepQueueGemma(
        [
            '{"tool": "step_complete", "params": {}, "reason": "완료"}',
            '{"tool": "step_complete", "params": {}, "reason": "완료"}',
            '{"tool": "step_complete", "params": {}, "reason": "완료"}',
            '{"tool": "step_complete", "params": {}, "reason": "완료"}',
        ]
    )
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "창", "w"),
            AutomationToolResult(False, "perceive fail"),
        ]
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=10)  # type: ignore[arg-type]
    msg = agent.run("테스트")
    assert "검증" in msg or "완료" in msg or "단계" in msg


def test_max_steps_exceeded(tmp_path: Path) -> None:
    repeat = '{"tool": "list_open_windows", "params": {}, "reason": "다시 확인"}'
    gemma = _RepeatGemma(repeat)
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda name, ctx: (
            _perceive_ok()
            if name == "perceive_desktop"
            else AutomationToolResult(True, "ok", "w1")
        )
    )

    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    msg = agent.run("반복 테스트")

    assert "단계 제한" in msg


def test_unknown_tool_parse_retries_then_stops(tmp_path: Path) -> None:
    gemma = _RepeatGemma('{"tool": "not_a_real_tool", "params": {}}')
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        return_value=AutomationToolResult(True, "ok")
    )

    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=10)  # type: ignore[arg-type]
    msg = agent.run("테스트")

    assert "이해하지 못했습니다" in msg or "단계 제한" in msg


def test_youtube_cu_planner_without_media_slots_still_uses_planner(tmp_path: Path) -> None:
    """media_action 슬롯 없으면 범용 CU 플래너 경로 유지."""
    import json

    from iris.automation.media_urls import build_youtube_search_url

    search_url = build_youtube_search_url("아이유")
    gemma = _StepQueueGemma(
        [
            json.dumps(
                {
                    "tool": "open_url",
                    "params": {"url": search_url},
                    "reason": "검색 결과 열기",
                },
                ensure_ascii=False,
            ),
            '{"tool": "step_failed", "params": {}, "reason": "재생 미완료"}',
        ]
    )
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    mock_run = MagicMock(
        side_effect=[
            AutomationToolResult(True, "창 목록", "Chrome"),
            _perceive_ok(),
            AutomationToolResult(True, "URL 열림", search_url[:80]),
            AutomationToolResult(True, "창 목록", "YouTube"),
            _perceive_ok(),
        ]
    )
    registry.run = mock_run  # type: ignore[method-assign]

    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=10)  # type: ignore[arg-type]
    msg = agent.run("유튜브에서 아이유 틀어줘", slots={"query": "아이유", "app_hint": "youtube"})

    planner = [c for c in gemma.calls if c and "Computer Use 플래너" in c[0].content]
    assert len(planner) >= 1
    assert "재생 미완료" in msg or "완료하지 못했습니다" in msg


def test_ask_user_returns_question_prefix(tmp_path: Path) -> None:
    gemma = _StepQueueGemma(
        [
            '{"tool": "ask_user", "params": {"question": "어떤 곡을 틀어드릴까요?"}, "reason": "query 없음"}',
        ]
    )
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "창", "w"),
            _perceive_ok(),
        ]
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    from iris.assistant.computer_use_agent import extract_user_question

    msg = agent.run("유튜브 틀어줘", slots={})
    assert extract_user_question(msg) == "어떤 곡을 틀어드릴까요?"


def test_run_includes_goal_slots_in_first_observation(tmp_path: Path) -> None:
    gemma = _StepQueueGemma(
        ['{"tool": "step_failed", "params": {}, "reason": "중단"}']
    )
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        return_value=AutomationToolResult(True, "ok")
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=3)  # type: ignore[arg-type]
    agent.run("테스트 목표", slots={"query": "hello"})
    planner = [c for c in gemma.calls if c and "Computer Use 플래너" in c[0].content]
    assert planner
    user_msg = planner[0][1].content
    assert "테스트 목표" in user_msg
    assert "hello" in user_msg


def test_simple_notepad_launch_skips_planner(tmp_path: Path) -> None:
    """메모장 켜줘 — launch_app 1스텝, 플래너·run_shell 미사용."""
    gemma = _RepeatGemma('{"tool": "run_shell", "params": {"command": "notepad"}}')
    assistant = _make_assistant(tmp_path, gemma)
    assistant._app_paths = {"notepad": r"C:\Windows\System32\notepad.exe"}
    registry = assistant._executor.tool_registry
    mock_run = MagicMock(
        return_value=AutomationToolResult(True, "메모장 실행 시작", "ok"),
    )
    registry.run = mock_run  # type: ignore[method-assign]

    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    msg = agent.run("메모장 켜줘")

    assert "실행" in msg
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == "launch_app"
    assert mock_run.call_args[0][1].approved is True
    planner = [c for c in gemma.calls if c and "Computer Use 플래너" in c[0].content]
    assert len(planner) == 0


def test_approval_required_sets_pending_tool(tmp_path: Path) -> None:
    gemma = _StepQueueGemma(
        ['{"tool": "run_shell", "params": {"command": "echo hi"}, "reason": "테스트"}']
    )
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "창", "w"),
            _perceive_ok(),
        ]
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    msg = agent.run("셸로 테스트")

    assert "진행할까요" in msg
    pending = assistant.ctx.pending_cu
    assert pending is not None
    assert pending.pending_tool_name == "run_shell"
    assert pending.pending_tool_params.get("command") == "echo hi"


def test_planner_chat_with_images_when_vlm_on(tmp_path: Path) -> None:
    """COMPUTER_USE_VLM_ENABLED — 플래너 루프에서 chat_with_images ≥1회."""
    gemma = _VisionStepGemma(
        [
            '{"tool": "step_complete", "params": {}, "reason": "완료했습니다."}',
        ]
    )
    settings = _cu_vlm_settings()
    assistant = _make_assistant(tmp_path, gemma, settings=settings)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "창", "Notepad"),
            _perceive_ok(),
        ]
    )
    with patch(
        "iris.assistant.computer_use_agent.capture_planner_screenshot",
        return_value=(_FAKE_PNG, "640x480 via active_window"),
    ):
        agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        agent.run("메모장에서 작업 확인")

    assert len(gemma.vision_calls) >= 1
    planner_msgs = gemma.vision_calls[0]
    assert "Computer Use 플래너" in planner_msgs[0].content
    user_msg = planner_msgs[1]
    assert user_msg.images and len(user_msg.images) == 1
    assert "screenshot_attached=yes" in user_msg.content
    assert "첨부 화면이 현재 PC 상태입니다" in user_msg.content


def test_planner_chat_only_when_vlm_off(tmp_path: Path) -> None:
    """VLM off — 기존 chat 경로만 (vision_calls 없음)."""
    gemma = _VisionStepGemma(
        [
            '{"tool": "step_complete", "params": {}, "reason": "끝."}',
        ]
    )
    settings = _cu_vlm_settings(computer_use_vlm_enabled=False)
    assistant = _make_assistant(tmp_path, gemma, settings=settings)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            AutomationToolResult(True, "창", "w"),
            _perceive_ok(),
        ]
    )
    agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
    agent.run("테스트")

    assert len(gemma.calls) >= 1
    assert len(gemma.vision_calls) == 0
    user_msg = gemma.calls[0][1]
    assert "screenshot_attached=no" in user_msg.content
    assert not user_msg.images


def test_media_play_skill_skips_cu_planner(tmp_path: Path) -> None:
    """skill_id=media_play — MediaPlaybackFlow만, CU 플래너·chat_with_images 없음."""
    gemma = _VisionStepGemma(
        ['{"tool": "open_url", "params": {}, "reason": "금지"}']
    )
    settings = _cu_vlm_settings()
    assistant = _make_assistant(tmp_path, gemma, settings=settings)
    registry = assistant._executor.tool_registry
    with patch(
        "iris.assistant.media_playback_flow.MediaPlaybackFlow.run",
        return_value="검색 결과를 열었습니다.",
    ) as mock_flow:
        agent = ComputerUseAgent(assistant, gemma, registry, max_steps=5)  # type: ignore[arg-type]
        msg = agent.run(
            "유튜브에서 아이유 검색",
            slots={"skill_id": "media_play", "search_query": "아이유"},
        )
    assert "검색" in msg
    mock_flow.assert_called_once()
    assert len(gemma.vision_calls) == 0
    planner = [c for c in gemma.calls if c and "Computer Use 플래너" in c[0].content]
    assert len(planner) == 0


def test_llm_unavailable_fallback(tmp_path: Path) -> None:
    gemma = _RepeatGemma(FALLBACK_KO)
    assistant = _make_assistant(tmp_path, gemma)
    agent = ComputerUseAgent(
        assistant,
        gemma,  # type: ignore[arg-type]
        assistant._executor.tool_registry,
        max_steps=5,
    )
    msg = agent.run("PC 사양 알려줘")
    assert FALLBACK_KO in msg or "로컬 언어 모델" in msg
