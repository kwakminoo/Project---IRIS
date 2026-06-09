"""integration_client — API 호출."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iris.integrations.integration_client import IntegrationClient, IntegrationRecord


def test_api_call_success() -> None:
    record = IntegrationRecord(
        name="demo",
        kind="api",
        base_url="https://api.example.com",
        command="",
        auth_header="",
        enabled=True,
    )
    client = IntegrationClient(record)
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.status_code = 200
    mock_resp.text = '{"ok":true}'
    with patch("httpx.Client") as mock_client_cls:
        inst = mock_client_cls.return_value.__enter__.return_value
        inst.post.return_value = mock_resp
        ok, msg, detail = client.call("v1/ping", {"q": "1"})
    assert ok is True
    assert "200" in msg
    assert "ok" in detail


def test_disabled_integration() -> None:
    record = IntegrationRecord(
        name="off",
        kind="api",
        base_url="http://localhost",
        command="",
        auth_header="",
        enabled=False,
    )
    ok, msg, _ = IntegrationClient(record).call("x", {})
    assert ok is False
    assert "비활성" in msg
