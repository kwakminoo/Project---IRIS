"""Computer Use 기계 Repair 템플릿 테스트."""

from __future__ import annotations

from iris.assistant.action_plan import ComputerUsePlanItem
from iris.assistant.cu_checkpoint_verify import CheckpointVerifyResult
from iris.assistant.cu_repair_templates import build_mechanical_repair_steps


def _verify(kind: str) -> CheckpointVerifyResult:
    return CheckpointVerifyResult(
        checkpoint_id="cp_focus",
        achieved=False,
        failure_kind=kind,
        progress_summary="",
        gap="gap",
        last_ok_index=1,
        resume_from_index=2,
        confidence=0.0,
    )


def test_mechanical_repair_wrong_focus() -> None:
    steps = build_mechanical_repair_steps(
        _verify("wrong_focus"),
        {"app_key": "notepad", "display_name": "메모장"},
        [],
    )
    assert len(steps) == 1
    assert steps[0].tool == "focus_window"
    assert steps[0].params["title_sub"] == "메모장"


def test_mechanical_repair_text_missing() -> None:
    steps = build_mechanical_repair_steps(
        _verify("text_missing"),
        {"display_name": "메모장", "text_to_type": "hello"},
        [],
    )
    assert len(steps) == 2
    assert steps[0].tool == "focus_window"
    assert steps[1].tool == "type_text"
    assert steps[1].params["text"] == "hello"


def test_mechanical_repair_missing_app_launch() -> None:
    steps = build_mechanical_repair_steps(
        _verify("missing_app"),
        {"app_key": "notepad", "display_name": "메모장"},
        ["windows: Chrome | Explorer"],
    )
    assert len(steps) == 1
    assert steps[0].tool == "launch_app"
    assert steps[0].params["app_key"] == "notepad"


def test_mechanical_repair_missing_app_focus_when_visible() -> None:
    steps = build_mechanical_repair_steps(
        _verify("missing_app"),
        {"app_key": "notepad", "display_name": "메모장"},
        ["windows: 메모장 | Chrome"],
    )
    assert len(steps) == 1
    assert steps[0].tool == "focus_window"


def test_mechanical_repair_unknown_returns_empty() -> None:
    assert build_mechanical_repair_steps(_verify("unknown"), {}, []) == ()
