"""cu_perception — PerceptionObservation 빌드·필드 매핑 테스트."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from iris.assistant.cu_perception import (
    PerceptionObservation,
    build_perception,
    has_valid_perception,
    perception_to_observation_line,
    windows_to_observation_line,
)
from iris.automation.tool_types import AutomationToolResult
from iris.config.settings import Settings


def _minimal_settings() -> Settings:
    return MagicMock(spec=Settings)


def test_build_perception_maps_tool_results() -> None:
    registry = MagicMock()
    pd_detail = json.dumps(
        {
            "perception_source": "uia",
            "active_window": "메모장",
            "summary": '{"edit":"empty"}',
            "captured_at": "2026-01-01T00:00:00+00:00",
        },
        ensure_ascii=False,
    )

    def _run(tool_name: str, _ctx: object) -> AutomationToolResult:
        if tool_name == "list_open_windows":
            return AutomationToolResult(True, "3개 창", "- 메모장\n- Chrome")
        if tool_name == "perceive_desktop":
            return AutomationToolResult(
                True,
                "perceive: uia | 메모장 | edit empty",
                pd_detail,
            )
        return AutomationToolResult(False, f"unknown tool {tool_name}")

    registry.run.side_effect = _run

    obs = build_perception(registry, _minimal_settings())

    assert obs.perception_source == "uia"
    assert obs.active_window_title == "메모장"
    assert "메모장" in obs.open_windows_summary
    assert obs.uia_snapshot_summary
    assert obs.captured_at > 0
    assert obs.raw_tool_results["list_open_windows"]["success"] is True
    assert obs.raw_tool_results["perceive_desktop"]["success"] is True


def test_has_valid_perception_requires_source_and_timestamp() -> None:
    assert not has_valid_perception(None)
    assert not has_valid_perception(
        PerceptionObservation(perception_source="unknown", captured_at=1.0)
    )
    assert has_valid_perception(
        PerceptionObservation(perception_source="ocr", captured_at=1.0)
    )


def test_observation_line_helpers() -> None:
    p = PerceptionObservation(
        active_window_title="Calc",
        open_windows_summary="- Calc",
        scene_summary="123",
        perception_source="ocr",
        captured_at=1.0,
    )
    assert perception_to_observation_line(p).startswith("perceive: ocr")
    assert windows_to_observation_line(p).startswith("windows:")
