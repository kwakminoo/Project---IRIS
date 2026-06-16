"""IDE Bridge 승인·연결 상태 테스트."""

from __future__ import annotations

from iris.infrastructure.ide.ide_bridge_client import IdeBridgeClient


def test_approval_required_not_dispatched_until_approved() -> None:
    client = IdeBridgeClient()
    client.start()
    try:
        cmd = client.queue_command("terminal.sendText", {"text": "echo hi"})
        assert cmd.status == "approval_required"
        polled = client._poll_commands()
        assert polled == []
        assert client.approve_command(cmd.id)
        polled2 = client._poll_commands()
        assert len(polled2) == 1
        assert polled2[0].id == cmd.id
    finally:
        client.stop()


def test_reject_command_never_dispatched() -> None:
    client = IdeBridgeClient()
    client.start()
    try:
        cmd = client.queue_command("editor.insertText", {"text": "x"})
        assert client.reject_command(cmd.id)
        assert client._poll_commands() == []
        done = client.get_command(cmd.id)
        assert done is not None
        assert done.status == "cancelled"
    finally:
        client.stop()


def test_connection_state_from_context() -> None:
    client = IdeBridgeClient()
    client.start()
    try:
        assert client.refresh_connection_state() == "disconnected"
        client._apply_context({"workspace_path": "/tmp", "active_file_uri": ""})
        assert client.connection_state() == "connected"
    finally:
        client.stop()
