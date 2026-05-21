"""tool_param_normalize — Computer Use params 별칭 정규화."""

from __future__ import annotations

from unittest.mock import MagicMock

from iris.assistant.action_plan import parse_computer_use_step
from iris.assistant.tool_param_normalize import normalize_computer_use_params
from iris.core.activity_privacy import summarize_tool_params


def test_focus_window_title_hint_to_title_sub() -> None:
    out = normalize_computer_use_params(
        "focus_window", {"title_hint": "YouTube"}
    )
    assert out["title_sub"] == "YouTube"
    assert "title_hint" in out


def test_focus_window_keeps_existing_title_sub() -> None:
    out = normalize_computer_use_params(
        "focus_window",
        {"title_sub": "Chrome", "title_hint": "YouTube"},
    )
    assert out["title_sub"] == "Chrome"


def test_uia_click_title_sub_to_window_title_sub() -> None:
    out = normalize_computer_use_params(
        "uia_click",
        {"title_sub": "YouTube", "name": "아이유 - 좋은 날"},
    )
    assert out["window_title_sub"] == "YouTube"
    assert out["name"] == "아이유 - 좋은 날"


def test_send_hotkey_key_to_keys_list() -> None:
    out = normalize_computer_use_params("send_hotkey", {"key": "enter"})
    assert out["keys"] == ["enter"]


def test_send_hotkey_key_combo_string() -> None:
    out = normalize_computer_use_params("send_hotkey", {"key": "ctrl+l"})
    assert out["keys"] == ["ctrl", "l"]


def test_send_hotkey_preserves_existing_keys() -> None:
    out = normalize_computer_use_params(
        "send_hotkey", {"keys": ["ctrl", "f"], "key": "enter"}
    )
    assert out["keys"] == ["ctrl", "f"]


def test_parse_computer_use_step_normalizes_focus_window() -> None:
    raw = '{"tool": "focus_window", "params": {"title_hint": "YouTube"}}'
    step = parse_computer_use_step(raw)
    assert step is not None
    assert step.params["title_sub"] == "YouTube"


def test_summarize_focus_window_uses_title_sub() -> None:
    normalized = normalize_computer_use_params(
        "focus_window", {"title_hint": "YouTube"}
    )
    s = summarize_tool_params("focus_window", normalized)
    assert s == "title_sub='YouTube'"


def test_focus_window_execute_receives_title_sub(tmp_path) -> None:
    """title_hint만 있는 플래너 JSON → Registry에 title_sub 전달."""
    from iris.assistant.agent_adapter import IrisAssistant
    from iris.assistant.computer_use_agent import ComputerUseAgent
    from iris.automation.action_executor import ActionExecutor
    from iris.automation.tool_types import AutomationToolResult
    from iris.storage.database import Database

    gemma_steps: list[str] = []

    class _Gemma:
        def chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            if messages and "Computer Use 플래너" in messages[0].content:
                return gemma_steps.pop(0)
            return "unused"

    gemma_steps.append(
        '{"tool": "focus_window", "params": {"title_hint": "YouTube"}, "reason": "창 포커스"}'
    )
    gemma_steps.append(
        '{"tool": "step_failed", "params": {}, "reason": "테스트 종료"}'
    )

    db = Database(path=tmp_path / "norm.db")
    assistant = IrisAssistant(db, ActionExecutor(db, {}), _Gemma(), {})  # type: ignore[arg-type]
    registry = assistant._executor.tool_registry
    captured: list[dict] = []

    def _run(name: str, ctx):  # type: ignore[no-untyped-def]
        captured.append(dict(ctx.params))
        if name == "focus_window":
            sub = str(ctx.params.get("title_sub") or "").strip()
            if not sub:
                return AutomationToolResult(False, "title_sub가 필요합니다.")
            return AutomationToolResult(True, "포커스 완료", "ok")
        return AutomationToolResult(True, "ok", "w")

    registry.run = MagicMock(side_effect=_run)  # type: ignore[method-assign]

    agent = ComputerUseAgent(assistant, _Gemma(), registry, max_steps=5)  # type: ignore[arg-type]
    agent.run("유튜브 창 포커스")

    focus_calls = [p for p in captured if p.get("title_sub") == "YouTube"]
    assert focus_calls, "focus_window must run with title_sub=YouTube"


def test_focus_window_missing_title_sub_fail_message() -> None:
    """정규화 후에도 힌트 없으면 tool_fail 메시지 유지."""
    from iris.assistant.computer_use_agent import ComputerUseAgent
    from iris.automation.tool_types import AutomationToolResult

    result = AutomationToolResult(False, "title_sub가 필요합니다.")
    obs = ComputerUseAgent._format_tool_observation("focus_window", result)
    assert "tool_fail: focus_window" in obs
    assert "title_sub가 필요합니다" in obs
