"""Windows GUI 통합 테스트 (CI 기본 제외)."""

from __future__ import annotations

import sys

import pytest

from iris.automation.tool_types import AutomationToolContext
from iris.automation.tools import PerceiveDesktopTool
from iris.config.settings import load_settings


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows GUI only")
def test_notepad_perceive_integration() -> None:
    """메모장 포커스 후 perceive_desktop (수동 환경에서 메모장이 열려 있으면 통과)."""
    settings = load_settings()
    tool = PerceiveDesktopTool()
    ctx = AutomationToolContext(
        settings=settings,
        params={"window_title_sub": "메모장", "focus_hint": "메모장"},
        approved=True,
    )
    res = tool.execute(ctx)
    # 메모장 없으면 실패할 수 있음 — 크래시만 없으면 됨
    assert res.message is not None


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows GUI only")
def test_send_hotkey_smoke() -> None:
    from iris.automation.tools import SendHotkeyTool

    tool = SendHotkeyTool()
    ctx = AutomationToolContext(
        params={"keys": ["esc"]},
        approved=True,
    )
    res = tool.execute(ctx)
    assert isinstance(res.success, bool)
