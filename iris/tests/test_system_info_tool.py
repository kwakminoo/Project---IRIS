"""get_system_info 도구·system_info 순수 함수."""

from pytest import MonkeyPatch

from iris.audio.speech_formatter import format_system_info_spoken
from iris.automation.system_info import (
    collect_system_info,
    system_info_brief_korean,
    verify_system_info_nonempty,
)
from iris.automation.tool_types import AutomationToolContext
from iris.automation.tools import GetSystemInfoTool


def test_verify_system_info_nonempty() -> None:
    assert verify_system_info_nonempty(
        {
            "os": "Windows 10",
            "cpu": "",
            "memory_total_gb": 0.0,
            "memory_available_gb": 0.0,
            "gpu": "",
            "disks": [],
        }
    )
    assert not verify_system_info_nonempty(
        {
            "os": "",
            "cpu": "",
            "memory_total_gb": 0.0,
            "memory_available_gb": 0.0,
            "gpu": "",
            "disks": [],
        }
    )


def test_system_info_brief_korean_includes_os() -> None:
    info = {
        "os": "Windows Test",
        "cpu": "Test CPU (8 논리 코어)",
        "memory_total_gb": 16.0,
        "memory_available_gb": 8.5,
        "gpu": "Test GPU",
        "disks": [{"mount": "C:\\", "total_gb": 256.0, "used_percent": 42.0}],
    }
    s = system_info_brief_korean(info)
    assert "Windows Test" in s
    assert "16" in s or "기가" in s


def test_get_system_info_tool_execute_stub(monkeypatch: MonkeyPatch) -> None:
    fake = {
        "os": "StubOS 1.0",
        "cpu": "StubCPU",
        "memory_total_gb": 8.0,
        "memory_available_gb": 4.0,
        "gpu": "",
        "disks": [],
    }
    monkeypatch.setattr("iris.automation.tools.collect_system_info", lambda: fake)

    tool = GetSystemInfoTool()
    ctx = AutomationToolContext(params={})
    res = tool.execute(ctx)
    assert res.success
    assert "StubOS" in res.message
    assert res.detail and "StubCPU" in res.detail


def test_format_system_info_spoken_short() -> None:
    raw = "운영체제는 Windows 11, CPU는 Intel. RAM은 전체 약 16.0기가바이트, 여유 약 8.0기가바이트예요."
    spoken = format_system_info_spoken(raw)
    assert len(spoken) > 0
    assert "Windows" in spoken or "기가" in spoken
