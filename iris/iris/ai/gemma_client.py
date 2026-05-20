"""Gemma 4 로컬 LLM 클라이언트 — Ollama /api/chat 기본, OpenAI 호환 경로 선택."""

from __future__ import annotations

import re
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
    "로컬 언어 모델에 연결할 수 없습니다. Ollama가 실행 중인지, "
    "OLLAMA_BASE_URL·GEMMA_MODEL_NAME(예: gemma4:e2b)을 확인해 주세요."
)

_STRIP_EMPTY_KO = (
    "모델이 내부 사고만 반환한 것 같습니다. "
    "질문을 조금 바꿔 다시 시도해 주세요."
)

# 모델이 노출하면 안 되는 사고/리즈닝 블록 제거
_THINK_BLOCK = re.compile(
    r"(?is)"
    r"(?:<think>.*?</think>"
    r"|<thinking>.*?</thinking>"
    r"|<reasoning>.*?</reasoning>"
    r"|<redacted_reasoning>.*?</redacted_reasoning>"
    r"|<{3}[\s\S]*?>{3})"
)

# LLM이 넣은 이모지·픽토그램 제거 (시스템 프롬프트와 이중 방어)
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U0001F600-\U0001F64F"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U000023CF-\U000023FF"
    "\U000024C2-\U0001F251"
    "\u200d"
    "\ufe0f"
    "]+",
    flags=re.UNICODE,
)


def _sanitize_visible_reply(text: str) -> str:
    """Thinking / 내부 리즈닝 태그·이모지 제거 후 사용자에게 보일 본문만 남김."""
    t = _THINK_BLOCK.sub("", text)
    t = _EMOJI_PATTERN.sub("", t)
    t = re.sub(r" +([,.!?;:])", r"\1", t)
    t = re.sub(r"  +", " ", t)
    # 모델이 태그 없이 "Thought:" 블록만 쓰는 경우 일부 제거
    t = re.sub(
        r"(?im)^\s*(?:thought|thinking|reasoning|내부\s*사고|사고\s*과정)\s*[:：]\s*.+$",
        "",
        t,
    )
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


class GemmaClient:
    """Ollama /api/chat 호출. 실패·빈 응답 시 한국어 fallback (앱 종료 없음)."""

    def __init__(self, settings: Settings, timeout_sec: float = 120.0) -> None:
        self._settings = settings
        self._timeout = timeout_sec

    def chat(self, messages: Sequence[ChatMessage]) -> str:
        if not self._settings.use_local_llm:
            return FALLBACK_KO
        try:
            if self._settings.gemma_backend == "openai_compatible":
                raw = self._chat_openai_compatible(messages)
            else:
                raw = self._chat_ollama(messages)
            cleaned = _sanitize_visible_reply(raw)
            if not cleaned:
                return _STRIP_EMPTY_KO if raw.strip() else FALLBACK_KO
            return cleaned
        except Exception:
            return FALLBACK_KO

    def _chat_ollama(self, messages: Sequence[ChatMessage]) -> str:
        # Ollama 전용 베이스 URL (기본 http://localhost:11434)
        base = self._settings.ollama_base_url.rstrip("/")
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
            return ""

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
                return ""
            msg = choices[0].get("message") or {}
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
            return ""
