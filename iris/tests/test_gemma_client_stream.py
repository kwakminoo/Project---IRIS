"""GemmaClient — Ollama 스트리밍·keep_alive."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.thinking_policy import LlmPurpose
from iris.config.settings import Settings


def _minimal_settings(**overrides: object) -> Settings:
    base = dict(
        ollama_base_url="http://localhost:11434",
        ollama_keep_alive="30m",
        gemma_api_base_url="http://localhost:11434",
        gemma_model_name="gemma4:e2b",
        ai_model_names=("gemma4:e2b",),
        gemma_backend="ollama",
        use_local_llm=True,
        thinking_mode="default",
    )
    base.update(overrides)
    return MagicMock(spec=Settings, **base)


def _stream_lines(*chunks: str) -> list[bytes]:
    lines: list[bytes] = []
    for ch in chunks:
        payload = {"message": {"content": ch}}
        lines.append(json.dumps(payload).encode("utf-8"))
    return lines


@patch("iris.ai.gemma_client.httpx.Client")
def test_ollama_stream_chunks_order_and_final_text(mock_client_cls: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _stream_lines("안", "녕", "하세요.")
    mock_response.raise_for_status = MagicMock()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.stream.return_value = mock_response
    mock_client_cls.return_value = mock_client

    settings = _minimal_settings()
    client = GemmaClient(settings, timeout_sec=5.0)
    seen: list[str] = []

    final = client.chat_stream(
        [ChatMessage("user", "hi")],
        purpose=LlmPurpose.DIALOGUE_CHAT,
        on_chunk=seen.append,
    )

    assert seen == ["안", "녕", "하세요."]
    assert final == "안녕하세요."
    payload = mock_client.stream.call_args.kwargs["json"]
    assert payload["stream"] is True


@patch("iris.ai.gemma_client.httpx.Client")
def test_ollama_payload_includes_keep_alive_when_set(mock_client_cls: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "ok"}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    settings = _minimal_settings(ollama_keep_alive="24h")
    client = GemmaClient(settings, timeout_sec=5.0)
    client.chat([ChatMessage("user", "hi")], purpose=LlmPurpose.DIALOGUE_CHAT)

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["keep_alive"] == "24h"


@patch("iris.ai.gemma_client.httpx.Client")
def test_ollama_payload_omits_keep_alive_when_empty(mock_client_cls: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "ok"}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    settings = _minimal_settings(ollama_keep_alive="")
    client = GemmaClient(settings, timeout_sec=5.0)
    client.chat([ChatMessage("user", "hi")])

    payload = mock_client.post.call_args.kwargs["json"]
    assert "keep_alive" not in payload
