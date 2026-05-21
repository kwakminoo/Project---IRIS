"""GemmaClient — Ollama /api/chat payload에 think 키 반영."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.thinking_policy import LlmPurpose
from iris.config.settings import Settings


def _minimal_settings(**overrides: object) -> Settings:
    base = dict(
        ollama_base_url="http://localhost:11434",
        gemma_api_base_url="http://localhost:11434",
        gemma_model_name="gemma4:e2b",
        ai_model_names=("gemma4:e2b",),
        gemma_backend="ollama",
        use_local_llm=True,
        thinking_mode="default",
    )
    base.update(overrides)
    # Settings는 frozen dataclass — 필수 필드가 많아 load_settings 대신 최소 mock
    return MagicMock(spec=Settings, **base)


@patch("iris.ai.gemma_client.httpx.Client")
def test_ollama_payload_includes_think_true(mock_client_cls: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "안녕하세요."}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    settings = _minimal_settings(thinking_mode="on")
    client = GemmaClient(settings, timeout_sec=5.0)
    client.chat(
        [ChatMessage("user", "hi")],
        purpose=LlmPurpose.DIALOGUE_CHAT,
    )

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["think"] is True


@patch("iris.ai.gemma_client.httpx.Client")
def test_ollama_payload_think_false_for_dialogue_default(mock_client_cls: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "응답"}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    settings = _minimal_settings(thinking_mode="default")
    client = GemmaClient(settings, timeout_sec=5.0)
    client.chat(
        [ChatMessage("user", "안녕")],
        purpose=LlmPurpose.DIALOGUE_CHAT,
    )

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["think"] is False


@patch("iris.ai.gemma_client.httpx.Client")
def test_ollama_payload_think_true_for_computer_use_default(mock_client_cls: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "{}"}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    settings = _minimal_settings(thinking_mode="default")
    client = GemmaClient(settings, timeout_sec=5.0)
    client.chat(
        [ChatMessage("user", "메모장 켜줘")],
        purpose=LlmPurpose.COMPUTER_USE,
        lane="computer_use",
    )

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["think"] is True
