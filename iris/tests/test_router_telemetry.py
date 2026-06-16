"""RouterTiming 계측 테스트."""

from __future__ import annotations

from iris.assistant.router_telemetry import RouterTiming, finish_timing, start_timing


def test_router_timing_summary_line() -> None:
    t = RouterTiming(turn_id="abc123")
    t.turn_received_at = 1.0
    t.turn_finished_at = 3.0
    t.selected_path = "FAST_CHAT"
    t.model_call_count = 1
    line = t.summary_line()
    assert "RouterTiming turn=abc123" in line
    assert "path=FAST_CHAT" in line
    assert "model_calls=1" in line


def test_start_and_finish_timing() -> None:
    t = start_timing("xyz")
    t.selected_path = "UNIFIED"
    finish_timing(t, db=None, telemetry_enabled=False)
    from iris.assistant.router_telemetry import get_timing

    assert get_timing("xyz") is None
