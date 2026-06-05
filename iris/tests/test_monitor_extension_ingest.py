"""Chrome 확장 ingest 서버 — 모니터링 off여도 기동."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iris.monitoring.browser_tab_monitor import BrowserTabMonitor
from iris.monitoring.monitor_manager import MonitorManager


def test_extension_http_starts_when_monitoring_disabled() -> None:
    settings = MagicMock()
    settings.enable_monitoring = False
    settings.iris_extension_host = "127.0.0.1"
    settings.iris_extension_port = 17777
    settings.iris_extension_token = ""
    settings.monitor_interval_seconds = 3

    mgr = MonitorManager(
        settings,
        db=MagicMock(),
        gemma=None,
        terminal_registry=MagicMock(),
        browser_monitor=BrowserTabMonitor(),
    )
    with patch(
        "iris.monitoring.monitor_manager.start_extension_server",
        return_value=(MagicMock(), MagicMock()),
    ) as start_srv:
        mgr.start()
        start_srv.assert_called_once()
    assert mgr._timer.isActive() is False
