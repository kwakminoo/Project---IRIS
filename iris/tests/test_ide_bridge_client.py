"""IDE Bridge 클라이언트 테스트."""

from __future__ import annotations

import json
import urllib.request

from iris.infrastructure.ide.ide_bridge_client import (
    IdeBridgeClient,
    IdeContext,
    is_context_attachment_allowed,
)


def test_bridge_reports_workspace_path() -> None:
    client = IdeBridgeClient()
    client.start()
    try:
        client._apply_context({
            "workspace_path": "/tmp/ws",
            "active_file_uri": "",
            "selected_text": "",
        })
        ctx = client.get_context()
        assert ctx.workspace_path == "/tmp/ws"
    finally:
        client.stop()


def test_bridge_reports_active_file() -> None:
    client = IdeBridgeClient()
    client.start()
    try:
        client._apply_context({
            "workspace_path": "/tmp",
            "active_file_uri": "file:///tmp/main.py",
            "active_file_language": "python",
            "selected_text": "",
        })
        ctx = client.get_context()
        assert ctx.active_file_uri.endswith("main.py")
        assert ctx.active_file_language == "python"
    finally:
        client.stop()


def test_bridge_reports_selected_text() -> None:
    client = IdeBridgeClient()
    client._apply_context({
        "selected_text": "def foo(): pass",
        "active_file_uri": "file:///tmp/a.py",
    })
    ctx = client.get_context()
    assert "foo" in ctx.selected_text


def test_secret_file_context_is_blocked() -> None:
    assert not is_context_attachment_allowed("file:///proj/.env")
    assert not is_context_attachment_allowed("file:///proj/id_rsa")
    assert is_context_attachment_allowed("file:///proj/main.py")


def test_bridge_http_get_context() -> None:
    client = IdeBridgeClient()
    client.start()
    try:
        client._apply_context({"workspace_path": "C:/ws", "active_file_uri": ""})
        url = f"{client.base_url}/context"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode())
        assert data["workspace_path"] == "C:/ws"
    finally:
        client.stop()


def test_bridge_cors_headers_on_commands() -> None:
    """Theia origin에서 /commands fetch 시 CORS 헤더가 있어야 한다."""
    import urllib.error

    client = IdeBridgeClient()
    client.start()
    try:
        req = urllib.request.Request(
            f"{client.base_url}/commands",
            headers={"Origin": "http://127.0.0.1:3100"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") == "*"
            data = json.loads(resp.read().decode())
        assert "commands" in data

        opt = urllib.request.Request(
            f"{client.base_url}/commands",
            method="OPTIONS",
            headers={
                "Origin": "http://127.0.0.1:3100",
                "Access-Control-Request-Method": "GET",
            },
        )
        try:
            with urllib.request.urlopen(opt, timeout=2) as resp:
                assert resp.status in (200, 204)
                assert resp.headers.get("Access-Control-Allow-Origin") == "*"
        except urllib.error.HTTPError as exc:
            # http.server may surface 204 oddly on some Python builds — headers still matter
            assert exc.headers.get("Access-Control-Allow-Origin") == "*"
    finally:
        client.stop()


def test_bridge_editor_state_get() -> None:
    client = IdeBridgeClient()
    client.start()
    try:
        client._apply_editor_state({
            "type": "iris.ide.editorStateChanged",
            "hasOpenEditor": True,
            "title": "x.py",
            "uri": "file:///x.py",
            "languageId": "python",
        })
        url = f"{client.base_url}/editor-state"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode())
        assert data["hasOpenEditor"] is True
        assert data["title"] == "x.py"
    finally:
        client.stop()


def test_context_summary_line() -> None:
    ctx = IdeContext(workspace_path="C:/IRIS", active_file_uri="file:///C:/IRIS/main.py")
    assert "IRIS" in ctx.summary_line()
