"""perceive_desktop·build_perception — load_test_settings 기준."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from iris.automation.perception_types import PerceptionObservation
from iris.automation.tool_types import AutomationToolContext
from iris.automation.tools import PerceiveDesktopTool, build_perception_observation
from tests.conftest import load_test_settings


@patch("iris.automation.tools.uia_reader.snapshot_window_uia", return_value=([], "", ""))
@patch("iris.automation.tools.read_screen_summary_text", return_value=(True, "ok", "OCR hello"))
@patch("iris.automation.tools.window_controller.get_active_window_title", return_value="Notepad")
def test_build_perception_ocr_when_uia_empty(
    _active: MagicMock,
    _ocr: MagicMock,
    _uia: MagicMock,
    tmp_path: Path,
) -> None:
    ctx = AutomationToolContext(
        settings=load_test_settings(tmp_path, computer_use_uia_enabled=True)
    )
    obs = build_perception_observation(ctx)
    assert obs.perception_source == "ocr"
    assert "OCR hello" in obs.summary
    assert "[monitor_target" not in obs.summary


@patch("iris.automation.tools.build_perception_observation")
def test_perceive_desktop_tool_message(mock_build: MagicMock, tmp_path: Path) -> None:
    mock_build.return_value = PerceptionObservation(
        active_window="Calc",
        summary='{"window":"Calc"}',
        perception_source="uia",
        monitor_hint='{"source":"target_match","target_title":"Calc"}',
    )
    tool = PerceiveDesktopTool()
    ctx = AutomationToolContext(settings=load_test_settings(tmp_path))
    res = tool.execute(ctx)
    assert res.success
    assert res.message.startswith("perceive:")
    detail = res.detail or ""
    assert "monitor_hint" in detail
