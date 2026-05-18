"""monitoring 패키지.

무거운 Qt/자동화 모듈은 lazy import로 노출해 테스트와 단위 모듈 import 시
순환 import가 발생하지 않게 한다.
"""

from __future__ import annotations

from typing import Any

from iris.monitoring.models import DetectionResult, MonitoredTarget, StatusCategory, TargetType

__all__ = [
    "BrowserTabMonitor",
    "DetectionResult",
    "MonitorManager",
    "MonitoredCommandHandle",
    "MonitoredTarget",
    "StatusCategory",
    "TargetType",
    "TerminalLogRegistry",
    "is_process_running",
    "start_monitored_command",
]


def __getattr__(name: str) -> Any:
    if name == "BrowserTabMonitor":
        from iris.monitoring.browser_tab_monitor import BrowserTabMonitor

        return BrowserTabMonitor
    if name == "MonitorManager":
        from iris.monitoring.monitor_manager import MonitorManager

        return MonitorManager
    if name in {"MonitoredCommandHandle", "TerminalLogRegistry", "start_monitored_command"}:
        from iris.monitoring import terminal_log_collector

        return getattr(terminal_log_collector, name)
    if name == "is_process_running":
        from iris.monitoring.legacy import is_process_running

        return is_process_running
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
