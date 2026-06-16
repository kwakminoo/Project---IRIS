"""라우터 성능 계측 — 사용자 원문·민감정보 미저장."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from iris.core.activity_sink import push_activity_line


@dataclass
class RouterTiming:
    """한 턴 라우팅·응답 타이밍 (메타데이터만)."""

    turn_id: str
    turn_received_at: float = 0.0
    pre_router_started_at: float = 0.0
    pre_router_finished_at: float = 0.0
    unified_router_started_at: float = 0.0
    unified_router_finished_at: float = 0.0
    frontier_started_at: float = 0.0
    frontier_finished_at: float = 0.0
    dialogue_started_at: float = 0.0
    dialogue_first_token_at: float = 0.0
    dialogue_finished_at: float = 0.0
    search_started_at: float = 0.0
    search_finished_at: float = 0.0
    execution_started_at: float = 0.0
    execution_finished_at: float = 0.0
    tts_started_at: float = 0.0
    ui_first_character_at: float = 0.0
    turn_finished_at: float = 0.0
    selected_path: str = ""
    unified_lane: str = ""
    frontier_invoked: bool = False
    frontier_reason: str = ""
    frontier_fallback_reason: str = ""
    model_call_count: int = 0
    router_model_call_count: int = 0
    dialogue_model_call_count: int = 0
    search_used: bool = False
    execution_used: bool = False

    def mark(self, attr: str) -> None:
        """타임스탬프 필드에 현재 시각 기록."""
        if hasattr(self, attr):
            setattr(self, attr, time.perf_counter())

    def inc_model_call(self, *, router: bool = False, dialogue: bool = False) -> None:
        self.model_call_count += 1
        if router:
            self.router_model_call_count += 1
        if dialogue:
            self.dialogue_model_call_count += 1

    def _ms(self, start: float, end: float) -> int:
        if start <= 0 or end <= 0 or end < start:
            return 0
        return int((end - start) * 1000)

    @property
    def total_latency_ms(self) -> int:
        if self.turn_received_at <= 0:
            return 0
        end = self.turn_finished_at or time.perf_counter()
        return self._ms(self.turn_received_at, end)

    @property
    def first_visible_response_ms(self) -> int:
        if self.turn_received_at <= 0 or self.ui_first_character_at <= 0:
            return 0
        return self._ms(self.turn_received_at, self.ui_first_character_at)

    def summary_line(self) -> str:
        unified_ms = self._ms(self.unified_router_started_at, self.unified_router_finished_at)
        frontier_ms = self._ms(self.frontier_started_at, self.frontier_finished_at)
        dialogue_ttft_ms = self._ms(self.dialogue_started_at, self.dialogue_first_token_at)
        parts = [
            f"RouterTiming turn={self.turn_id}",
            f"path={self.selected_path or 'unknown'}",
            f"model_calls={self.model_call_count}",
            f"unified_ms={unified_ms}",
            f"frontier_ms={frontier_ms}",
            f"dialogue_ttft_ms={dialogue_ttft_ms}",
            f"first_visible_ms={self.first_visible_response_ms}",
            f"total_ms={self.total_latency_ms}",
        ]
        if self.frontier_invoked and self.frontier_reason:
            parts.append(f"frontier_reason={self.frontier_reason}")
        if self.frontier_fallback_reason:
            parts.append(f"frontier_fallback={self.frontier_fallback_reason}")
        return " ".join(parts)

    def to_log_json(self) -> str:
        payload: dict[str, Any] = {
            "turn_id": self.turn_id,
            "selected_path": self.selected_path,
            "unified_lane": self.unified_lane,
            "frontier_invoked": self.frontier_invoked,
            "frontier_reason": self.frontier_reason,
            "frontier_fallback_reason": self.frontier_fallback_reason,
            "model_call_count": self.model_call_count,
            "router_model_call_count": self.router_model_call_count,
            "dialogue_model_call_count": self.dialogue_model_call_count,
            "search_used": self.search_used,
            "execution_used": self.execution_used,
            "total_latency_ms": self.total_latency_ms,
            "first_visible_response_ms": self.first_visible_response_ms,
        }
        return json.dumps(payload, ensure_ascii=False)


# 턴별 전역 컨텍스트 (UI 스레드·워커 간 turn_id로 조회)
_active_timings: dict[str, RouterTiming] = {}


def start_timing(turn_id: str) -> RouterTiming:
    timing = RouterTiming(turn_id=turn_id)
    timing.turn_received_at = time.perf_counter()
    _active_timings[turn_id] = timing
    return timing


def get_timing(turn_id: str) -> RouterTiming | None:
    return _active_timings.get(turn_id)


def finish_timing(
    timing: RouterTiming,
    *,
    db: Any | None = None,
    telemetry_enabled: bool = True,
) -> None:
    """계측 종료 — Activity Log + SQLite (선택)."""
    if timing.turn_finished_at <= 0:
        timing.mark("turn_finished_at")
    line = timing.summary_line()
    if telemetry_enabled:
        push_activity_line(line)
        if db is not None:
            try:
                db.insert_log("router_timing", timing.turn_id, timing.to_log_json())
            except Exception:
                pass
    _active_timings.pop(timing.turn_id, None)


def mark_ui_first_character(turn_id: str) -> None:
    timing = _active_timings.get(turn_id)
    if timing is not None and timing.ui_first_character_at <= 0:
        timing.mark("ui_first_character_at")


def mark_ui_first_character_active() -> None:
    """진행 중인 턴(최근)에 UI 첫 글자 시각 기록."""
    if not _active_timings:
        return
    turn_id = next(reversed(_active_timings))
    mark_ui_first_character(turn_id)
