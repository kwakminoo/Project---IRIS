"""cu_mechanical_verify — 기계 체크포인트 검증 단위 테스트."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from iris.assistant.action_plan import ComputerUsePlanItem
from iris.assistant.cu_mechanical_verify import (
    mechanical_verify_checkpoint,
    title_matches_app,
)
from iris.assistant.cu_perception import PerceptionObservation


def _ctx(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "last_focus_hwnd": 0,
        "last_type_verify": None,
        "observations": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _perception(**kwargs: object) -> PerceptionObservation:
    base = {
        "active_window_title": "",
        "open_windows_summary": "",
        "scene_summary": "",
        "perception_source": "ocr",
        "captured_at": 1.0,
    }
    base.update(kwargs)
    return PerceptionObservation(**base)


def test_title_matches_app_notepad() -> None:
    assert title_matches_app("notepad", "무제 - 메모장", display_name="메모장")
    assert title_matches_app("notepad", "Notepad")
    assert not title_matches_app("notepad", "Calculator")


def test_cp_app_open_success() -> None:
    p = _perception(
        active_window_title="무제 - 메모장",
        open_windows_summary='[{"title":"무제 - 메모장"}]',
    )
    result = mechanical_verify_checkpoint(
        "cp_app_open",
        perception=p,
        slots={"app_key": "notepad", "display_name": "메모장"},
        executed_plans=(),
        cu_ctx=_ctx(),
    )
    assert result.status == "success"
    assert result.confidence == 1.0


def test_cp_app_open_failed() -> None:
    p = _perception(open_windows_summary="Calculator")
    result = mechanical_verify_checkpoint(
        "cp_app_open",
        perception=p,
        slots={"app_key": "notepad", "display_name": "메모장"},
        executed_plans=(),
        cu_ctx=_ctx(),
    )
    assert result.status == "failed"
    assert result.failure_kind == "missing_app"


def test_cp_app_open_inconclusive_no_slots() -> None:
    result = mechanical_verify_checkpoint(
        "cp_app_open",
        perception=_perception(open_windows_summary="메모장"),
        slots={},
        executed_plans=(),
        cu_ctx=_ctx(),
    )
    assert result.status == "inconclusive"


def test_cp_focus_success_by_title() -> None:
    p = _perception(active_window_title="무제 - 메모장")
    result = mechanical_verify_checkpoint(
        "cp_focus",
        perception=p,
        slots={"app_key": "notepad", "display_name": "메모장"},
        executed_plans=(),
        cu_ctx=_ctx(),
    )
    assert result.status == "success"
    assert result.confidence == 1.0


def test_cp_focus_failed_wrong_window() -> None:
    p = _perception(active_window_title="Calculator")
    result = mechanical_verify_checkpoint(
        "cp_focus",
        perception=p,
        slots={"app_key": "notepad", "display_name": "메모장"},
        executed_plans=(),
        cu_ctx=_ctx(),
    )
    assert result.status == "failed"
    assert result.failure_kind == "wrong_focus"


@patch("iris.assistant.cu_mechanical_verify._foreground_hwnd", return_value=42)
def test_cp_focus_success_by_hwnd(mock_fg: MagicMock) -> None:
    p = _perception(active_window_title="")
    result = mechanical_verify_checkpoint(
        "cp_focus",
        perception=p,
        slots={},
        executed_plans=(),
        cu_ctx=_ctx(last_focus_hwnd=42),
    )
    assert result.status == "success"
    mock_fg.assert_called_once()


@patch("iris.assistant.cu_mechanical_verify.read_focused_field_text", return_value=(True, "hello"))
def test_cp_text_typed_success_uia(mock_read: MagicMock) -> None:
    plans = (
        ComputerUsePlanItem(3, "type_text", {"text": "hello"}, "입력", "cp_text_typed"),
    )
    result = mechanical_verify_checkpoint(
        "cp_text_typed",
        perception=_perception(active_window_title="무제 - 메모장"),
        slots={"text_to_type": "hello"},
        executed_plans=plans,
        cu_ctx=_ctx(),
    )
    assert result.status == "success"
    assert result.confidence == 1.0
    mock_read.assert_called_once()


def test_cp_text_typed_success_last_type_verify_notepad_hello() -> None:
    """메모장+hello 시나리오 — LLM 없이 last_type_verify로 success."""
    plans = (
        ComputerUsePlanItem(3, "type_text", {"text": "hello"}, "입력", "cp_text_typed"),
    )
    result = mechanical_verify_checkpoint(
        "cp_text_typed",
        perception=_perception(
            active_window_title="무제 - 메모장",
            scene_summary="Notepad | hello",
        ),
        slots={"app_key": "notepad", "text": "hello"},
        executed_plans=plans,
        cu_ctx=_ctx(last_type_verify=True),
    )
    assert result.status == "success"
    assert result.confidence == 1.0


@patch("iris.assistant.cu_mechanical_verify.read_focused_field_text", return_value=(False, ""))
def test_cp_text_typed_inconclusive_scene_hint(mock_read: MagicMock) -> None:
    result = mechanical_verify_checkpoint(
        "cp_text_typed",
        perception=_perception(scene_summary="ocr | Notepad | hello world"),
        slots={"text_to_type": "hello"},
        executed_plans=(),
        cu_ctx=_ctx(),
    )
    assert result.status == "inconclusive"
    assert result.confidence == 0.5
    mock_read.assert_called_once()


@patch("iris.assistant.cu_mechanical_verify.read_focused_field_text", return_value=(True, "wrong"))
def test_cp_text_typed_failed_mismatch(mock_read: MagicMock) -> None:
    result = mechanical_verify_checkpoint(
        "cp_text_typed",
        perception=_perception(),
        slots={"text_to_type": "hello"},
        executed_plans=(),
        cu_ctx=_ctx(last_type_verify=False),
    )
    assert result.status == "failed"
    assert result.failure_kind == "text_partial"


def test_cp_message_sent_inconclusive() -> None:
    result = mechanical_verify_checkpoint(
        "cp_message_sent",
        perception=_perception(),
        slots={},
        executed_plans=(),
        cu_ctx=_ctx(),
    )
    assert result.status == "inconclusive"


def test_cp_final_success_when_sub_checkpoints_ok() -> None:
    obs = [
        "checkpoint_ok: cp_app_open | 메모장",
        "checkpoint_ok: cp_focus | 포커스",
        "checkpoint_ok: cp_text_typed | hello",
    ]
    result = mechanical_verify_checkpoint(
        "cp_final",
        perception=_perception(),
        slots={},
        executed_plans=(),
        cu_ctx=_ctx(observations=obs),
    )
    assert result.status == "success"
