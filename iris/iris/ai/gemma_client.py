"""Gemma 4 로컬 HTTP 클라이언트 (Ollama / OpenAI 호환)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import httpx

from iris.config.settings import Settings

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


FALLBACK_KO = (
    "로컬 언어 모델에 연결할 수 없습니다. Ollama 또는 LM Studio가 실행 중인지, "
    "GEMMA_API_BASE_URL 과 GEMMA_MODEL_NAME 을 확인해 주세요."
)


class GemmaClient:
    """로컬 LLM 호출. 실패 시 한국어 fallback."""

    def __init__(self, settings: Settings, timeout_sec: float = 60.0) -> None:
        self._settings = settings
        self._timeout = timeout_sec

    def chat(self, messages: Sequence[ChatMessage]) -> str:
        if not self._settings.use_local_llm:
            return FALLBACK_KO
        try:
            if self._settings.gemma_backend == "openai_compatible":
                return self._chat_openai_compatible(messages)
            return self._chat_ollama(messages)
        except (httpx.HTTPError, OSError, ValueError, KeyError):
            return FALLBACK_KO

    def _chat_ollama(self, messages: Sequence[ChatMessage]) -> str:
        base = self._settings.gemma_api_base_url.rstrip("/")
        url = f"{base}/api/chat"
        payload = {
            "model": self._settings.gemma_model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            msg = data.get("message") or {}
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
            return FALLBACK_KO

    def _chat_openai_compatible(self, messages: Sequence[ChatMessage]) -> str:
        base = self._settings.gemma_api_base_url.rstrip("/")
        url = f"{base}/v1/chat/completions"
        payload = {
            "model": self._settings.gemma_model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0.4,
        }
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return FALLBACK_KO
            msg = choices[0].get("message") or {}
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
            return FALLBACK_KO
