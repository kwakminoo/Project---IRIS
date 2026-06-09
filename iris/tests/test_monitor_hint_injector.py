"""Phase 6 — monitoring 힌트 → ComputerUseContext.observations 주입."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from iris.monitoring.cu_hint_injector import (
    append_monitor_hint_observations,
    collect_monitor_hints,
    monitor_hint_observation_line,
)
from iris.monitoring.models import StatusCategory
from iris.monitoring.proactive_suggestion import (
    ProactiveMonitorResult,
    dispatch_proactive_monitor_event,
    should_suppress_proactive_chat,
    try_proactive_suggestion_from_event,
)
from iris.monitoring.target_hints import (
    build_perceive_monitor_hint_json,
    match_monitor_target,
)


class _FakeRow:
    def __init__(self, data: dict) -> None:
        self._data = data

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def __getitem__(self, key: str):
        return self._data[key]


def _fake_db(
    *,
    targets: list[dict] | None = None,
    events: list[dict] | None = None,
    target_states: dict[int, dict] | None = None,
) -> MagicMock:
    db = MagicMock()
    db.list_targets.return_value = [_FakeRow(r) for r in (targets or [])]
    db.list_recent_events.return_value = [_FakeRow(r) for r in (events or [])]

    def _get_state(tid: int):
        st = (target_states or {}).get(tid)
        return _FakeRow(st) if st else None

    db.get_recent_target_state.side_effect = _get_state
    return db


def test_match_monitor_target_structured() -> None:
    hints = [{"title": "Cursor", "process_name": "Cursor.exe"}]
    matched = match_monitor_target(hints, "Cursor - main.py")
    assert matched is not None
    assert matched["title"] == "Cursor"


def test_build_perceive_monitor_hint_json() -> None:
    hints = [{"title": "메모장", "process_name": "notepad.exe"}]
    raw = build_perceive_monitor_hint_json(hints, "메모장 - hello.txt")
    data = json.loads(raw)
    assert data["source"] == "target_match"
    assert data["target_title"] == "메모장"


def test_collect_monitor_hints_from_event() -> None:
    db = _fake_db(
        events=[
            {
                "id": 7,
                "target_id": 2,
                "target_title": "터미널",
                "category": StatusCategory.ERROR_DETECTED.value,
                "reason": "Traceback",
                "recommended_action": "로그 확인",
            }
        ]
    )
    hints = collect_monitor_hints(db, active_window_title="터미널 - pwsh")
    assert hints
    assert hints[0]["source"] == "recent_event"
    assert hints[0]["category"] == StatusCategory.ERROR_DETECTED.value


def test_collect_monitor_hints_target_match_and_status() -> None:
    db = _fake_db(
        targets=[
            {
                "id": 1,
                "title": "Cursor",
                "process_name": "Cursor.exe",
                "status": StatusCategory.ERROR_DETECTED.value,
                "last_event": "build failed",
            }
        ],
        target_states={
            1: {
                "status": StatusCategory.TASK_STALLED.value,
                "last_changed_at": "2026-06-09T12:00:00",
            }
        },
    )
    hints = collect_monitor_hints(db, active_window_title="Cursor - IRIS")
    sources = {h["source"] for h in hints}
    assert "target_match" in sources
    assert "target_status" in sources


def test_monitor_hint_observation_line_format() -> None:
    line = monitor_hint_observation_line(
        [{"source": "recent_event", "category": "ERROR_DETECTED", "reason": "x"}]
    )
    assert line is not None
    assert line.startswith("monitor_hint: ")
    payload = json.loads(line[len("monitor_hint: ") :])
    assert payload["source"] == "recent_event"


def test_append_monitor_hint_observations() -> None:
    db = _fake_db(
        events=[
            {
                "id": 1,
                "target_id": None,
                "target_title": "Chrome",
                "category": StatusCategory.RESPONSE_READY.value,
                "reason": "done",
                "recommended_action": "탭 확인",
            }
        ]
    )
    obs: list[str] = ["perceive: uia | Chrome | ok"]
    added = append_monitor_hint_observations(obs, db, active_window_title="Chrome")
    assert added is True
    assert any(o.startswith("monitor_hint:") for o in obs)


def test_proactive_suggestion_returns_message() -> None:
    msg = try_proactive_suggestion_from_event(
        category="ERROR_DETECTED",
        target_title="Cursor",
        recommended_action="로그 확인",
        alert_message="",
        dialogue_ctx=None,
    )
    assert msg is not None
    assert "Cursor" in msg


def test_proactive_suppressed_during_pending_cu() -> None:
    from iris.core.context_manager import DialogueContext, PendingComputerUseGoal

    ctx = DialogueContext()
    ctx.pending_cu = PendingComputerUseGoal(goal="메모장 hello")
    assert should_suppress_proactive_chat(ctx) is True
    assert (
        try_proactive_suggestion_from_event(
            category="ERROR_DETECTED",
            target_title="Cursor",
            recommended_action="확인",
            dialogue_ctx=ctx,
        )
        is None
    )


def test_dispatch_proactive_monitor_event(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from iris.assistant.dialogue_agent import DialogueAgent
    from iris.core.context_manager import DialogueContext, DialogueStep
    from iris.storage.database import Database

    db = Database(path=tmp_path / "pro.db")
    ctx = DialogueContext()
    ctx.step = DialogueStep.NONE
    assistant = MagicMock()
    assistant.ctx = ctx
    assistant.memory = MagicMock()
    assistant.set_monitor_pending.return_value = True
    dialogue = DialogueAgent(assistant, MagicMock())  # type: ignore[arg-type]

    result = dispatch_proactive_monitor_event(
        assistant,
        dialogue,
        title="터미널",
        message="",
        category="APPROVAL_WAITING",
        target_id=1,
        focus_hint="터미널",
        recommended="y 입력",
        event_id=3,
    )
    assert isinstance(result, ProactiveMonitorResult)
    assert result.show_in_chat is True
    assert result.pending_set is True
    assert "터미널" in result.proposal
