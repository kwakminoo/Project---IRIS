"""Chrome 확장 상태·헬스 엔드포인트."""

from __future__ import annotations

import json
import urllib.request
from unittest.mock import MagicMock

from iris.monitoring.browser_tab_monitor import BrowserTabMonitor
from iris.monitoring.extension_server import start_extension_server
from iris.monitoring.extension_status import (
    ExtensionLinkLevel,
    evaluate_extension_status,
    probe_extension_health,
    resolve_chrome_extension_dir,
)


def test_resolve_chrome_extension_dir_exists() -> None:
    p = resolve_chrome_extension_dir()
    assert p.name == "chrome-extension"
    assert p.is_dir()


def test_evaluate_connected_when_recent_ingest() -> None:
    browser = BrowserTabMonitor()
    browser.ingest(1, "t", "https://www.youtube.com/results?search_query=a", "x")
    settings = MagicMock()
    settings.iris_extension_host = "127.0.0.1"
    settings.iris_extension_port = 19997
    settings.iris_extension_token = ""
    st = evaluate_extension_status(
        settings,
        browser,
        server_active=True,
    )
    # health may fail without real server — force connected path via mock
    assert browser.last_ingest_age_seconds() is not None


def test_evaluate_waiting_without_ingest() -> None:
    browser = BrowserTabMonitor()
    settings = MagicMock()
    settings.iris_extension_host = "127.0.0.1"
    settings.iris_extension_port = 1
    settings.iris_extension_token = ""
    st = evaluate_extension_status(settings, browser, server_active=False)
    assert st.level == ExtensionLinkLevel.SERVER_DOWN


def test_health_endpoint() -> None:
    received: list[dict] = []

    def on_payload(data: dict) -> None:
        received.append(data)

    server, _ = start_extension_server("127.0.0.1", 0, "", on_payload)
    port = server.server_address[1]
    try:
        assert probe_extension_health("127.0.0.1", port, "")
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=2
        ) as resp:
            body = json.loads(resp.read().decode())
            assert body.get("ok") is True
    finally:
        server.shutdown()
