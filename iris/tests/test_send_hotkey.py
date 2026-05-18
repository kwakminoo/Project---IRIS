"""send_hotkey 도구 테스트."""

from __future__ import annotations

from unittest.mock import patch

from iris.automation.tool_types import AutomationToolContext
from iris.automation.tools import SendHotkeyTool


@patch(
    "iris.automation.tools.keyboard_mouse_controller.send_hotkey_approved",
    return_value=(True, "ctrl+f"),
)
def test_send_hotkey_list_keys(mock_hotkey: object) -> None:
    tool = SendHotkeyTool()
    ctx = AutomationToolContext(
        params={"keys": ["ctrl", "f"]},
        approved=True,
    )
    res = tool.execute(ctx)
    assert res.success
    assert "ctrl" in (res.detail or res.message)
