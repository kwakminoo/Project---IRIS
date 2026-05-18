"""Early ack merge·Worker 로직 단위 테스트 (Qt 없음)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.turn_coordinator import (
    TurnCoordinator,
    build_spoken_followup,
    build_user_visible,
)
from iris.automation.action_executor import ActionExecutor
from iris.storage.database import Database
from iris.ui.workers import AgentWorker


def test_merge_spoken_followup_strips_ack() -> None:
    ack = "유튜브를 열게요."
    exec_reply = "Iris: 브라우저에서 URL을 열었습니다."
    full = build_user_visible(ack, exec_reply)
    followup = build_spoken_followup(ack, exec_reply)

    assert "유튜브를 열게요" in full
    assert "브라우저" in full
    assert "유튜브를 열게요" not in followup
    assert "브라우저" in followup


def test_worker_no_early_ack_when_coordinator_has_none(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "chat.db")
    assistant = IrisAssistant(db, ActionExecutor(db, {}), object(), {})  # type: ignore[arg-type]
    worker = AgentWorker(assistant, "안녕")
    emitted: list[str] = []
    worker.early_ack.connect(lambda s: emitted.append(s))

    with patch.object(
        TurnCoordinator,
        "run_turn",
        return_value=type(
            "R",
            (),
            {
                "user_visible": "Iris: hi",
                "store_history": False,
                "had_early_ack": False,
                "early_ack": None,
                "spoken_followup": None,
                "delegate_search": False,
                "search_intent_name": None,
            },
        )(),
    ):
        worker.run()

    assert emitted == []


def test_worker_uses_coordinator_callback(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "multi.db")
    assistant = IrisAssistant(db, ActionExecutor(db, {}), object(), {})  # type: ignore[arg-type]
    worker = AgentWorker(assistant, "유튜브 틀어줘")
    early: list[str] = []
    finished: list[tuple[str, bool, bool, str]] = []
    worker.early_ack.connect(early.append)
    worker.finished_reply.connect(
        lambda r, sh, he, sf: finished.append((r, sh, he, sf))
    )

    with patch.object(
        TurnCoordinator,
        "run_turn",
        return_value=type(
            "R",
            (),
            {
                "user_visible": "Iris: 유튜브를 열게요. 브라우저에서 URL을 열었습니다.",
                "store_history": False,
                "had_early_ack": True,
                "early_ack": "유튜브를 열게요.",
                "spoken_followup": "Iris: 브라우저에서 URL을 열었습니다.",
                "delegate_search": False,
                "search_intent_name": None,
            },
        )(),
    ) as mock_run:
        worker.run()

    assert mock_run.call_count == 1
    assert mock_run.call_args.kwargs.get("on_early_ack") is not None
    assert early == []
    assert len(finished) == 1
    assert finished[0][2] is True
    assert "유튜브를 열게요" not in finished[0][3]
