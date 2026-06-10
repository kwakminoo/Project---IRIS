"""Gemma 4 로컬 LLM 클라이언트 — Ollama /api/chat 기본, OpenAI 호환 경로 선택."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Sequence

import httpx

from iris.ai.thinking_policy import LlmPurpose, resolve_think
from iris.config.settings import Settings
from iris.core.activity_sink import push_activity_line

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str
    # PNG/JPEG bytes — Ollama user 메시지 images 필드로 전송 (DB·디스크 저장 없음)
    images: tuple[bytes, ...] = field(default_factory=tuple)


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
  # U+24C2~U+1F251 단일 범위는 한글(AC00~D7A3)까지 포함해 본문이 통째로 삭제됨 — BMP enclosed만
    "\U00002460-\U000024FF"
    "\U0001F100-\U0001F1FF"
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


def _ollama_message_dict(m: ChatMessage, *, include_images: bool) -> dict[str, object]:
    """Ollama /api/chat messages 항목 — images는 user 역할에만."""
    out: dict[str, object] = {"role": m.role, "content": m.content}
    if include_images and m.images and m.role == "user":
        out["images"] = [base64.b64encode(img).decode("ascii") for img in m.images]
    return out


class GemmaClient:
    """Ollama /api/chat 호출. 실패·빈 응답 시 한국어 fallback (앱 종료 없음)."""

    def __init__(self, settings: Settings, timeout_sec: float = 120.0) -> None:
        self._settings = settings
        self._timeout = timeout_sec

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        purpose: LlmPurpose = LlmPurpose.GENERIC,
        lane: str | None = None,
        model_override: str | None = None,
    ) -> str:
        if not self._settings.use_local_llm:
            push_activity_line("LLM: request skipped (USE_LOCAL_LLM off).")
            return FALLBACK_KO
        think = resolve_think(self._settings.thinking_mode, purpose, lane=lane)
        lane_bit = f" lane={lane}" if lane else ""
        has_images = any(m.images for m in messages)
        model = (model_override or "").strip() or self._settings.gemma_model_name
        push_activity_line(
            f"LLM: think={str(think).lower()} purpose={purpose.value}{lane_bit} "
            f"backend={self._settings.gemma_backend!r} "
            f"model={model!r} messages={len(messages)} images={has_images}."
        )
        try:
            if self._settings.gemma_backend == "openai_compatible":
                raw = self._chat_openai_compatible(messages, model=model)
            else:
                raw = self._chat_ollama(
                    messages, think=think, model=model, include_images=has_images
                )
            cleaned = _sanitize_visible_reply(raw)
            if not cleaned:
                push_activity_line(
                    "LLM: empty visible reply after sanitization (fallback path)."
                )
                return _STRIP_EMPTY_KO if raw.strip() else FALLBACK_KO
            push_activity_line(f"LLM: response done chars={len(cleaned)}.")
            return cleaned
        except Exception:
            push_activity_line("LLM: request failed (transport or HTTP error).")
            return FALLBACK_KO

    def chat_stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        purpose: LlmPurpose = LlmPurpose.GENERIC,
        lane: str | None = None,
        model_override: str | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """Ollama stream: true — 청크마다 on_chunk, 최종 sanitize 문자열 반환."""
        if not self._settings.use_local_llm:
            push_activity_line("LLM: stream skipped (USE_LOCAL_LLM off).")
            if on_chunk:
                on_chunk(FALLBACK_KO)
            return FALLBACK_KO
        think = resolve_think(self._settings.thinking_mode, purpose, lane=lane)
        lane_bit = f" lane={lane}" if lane else ""
        has_images = any(m.images for m in messages)
        model = (model_override or "").strip() or self._settings.gemma_model_name
        push_activity_line(
            f"LLM: stream think={str(think).lower()} purpose={purpose.value}{lane_bit} "
            f"backend={self._settings.gemma_backend!r} "
            f"model={model!r} messages={len(messages)} images={has_images}."
        )
        try:
            if self._settings.gemma_backend == "openai_compatible":
                raw = self._chat_openai_compatible(messages, model=model)
                if on_chunk and raw:
                    on_chunk(raw)
            else:
                raw = self._chat_ollama_stream(
                    messages,
                    think=think,
                    model=model,
                    include_images=has_images,
                    on_chunk=on_chunk,
                )
            cleaned = _sanitize_visible_reply(raw)
            if not cleaned:
                push_activity_line(
                    "LLM: empty visible stream reply after sanitization (fallback)."
                )
                fallback = _STRIP_EMPTY_KO if raw.strip() else FALLBACK_KO
                if on_chunk and not raw.strip():
                    on_chunk(fallback)
                return fallback
            push_activity_line(f"LLM: stream done chars={len(cleaned)}.")
            return cleaned
        except Exception:
            push_activity_line("LLM: stream failed (transport or HTTP error).")
            if on_chunk:
                on_chunk(FALLBACK_KO)
            return FALLBACK_KO

    def chat_with_images(
        self,
        messages: Sequence[ChatMessage],
        *,
        purpose: LlmPurpose = LlmPurpose.GENERIC,
        lane: str | None = None,
        model_override: str | None = None,
        vision_fallback_to_text: bool = True,
    ) -> tuple[str, bool]:
        """멀티모달 chat — (응답, vision_used). 비전 실패 시 텍스트-only 재시도."""
        has_images = any(m.images for m in messages)
        if not has_images:
            return (
                self.chat(
                    messages,
                    purpose=purpose,
                    lane=lane,
                    model_override=model_override,
                ),
                False,
            )
        if not self._settings.use_local_llm:
            return FALLBACK_KO, False
        think = resolve_think(self._settings.thinking_mode, purpose, lane=lane)
        lane_bit = f" lane={lane}" if lane else ""
        model = (model_override or "").strip() or self._settings.gemma_model_name
        if self._settings.gemma_backend == "openai_compatible":
            push_activity_line(
                f"LLM: vision_unavailable backend=openai_compatible "
                f"purpose={purpose.value}{lane_bit} images={has_images}."
            )
            stripped = [ChatMessage(m.role, m.content) for m in messages]
            return (
                self.chat(
                    stripped,
                    purpose=purpose,
                    lane=lane,
                    model_override=model_override,
                ),
                False,
            )
        push_activity_line(
            f"LLM: think={str(think).lower()} purpose={purpose.value}{lane_bit} "
            f"backend={self._settings.gemma_backend!r} "
            f"model={model!r} messages={len(messages)} images={has_images}."
        )
        try:
            raw = self._chat_ollama(
                messages, think=think, model=model, include_images=True
            )
            cleaned = _sanitize_visible_reply(raw)
            if not cleaned:
                raise ValueError("empty vision reply")
            return cleaned, True
        except Exception:
            if not vision_fallback_to_text:
                push_activity_line("LLM: vision request failed.")
                return FALLBACK_KO, False
            push_activity_line("LLM: rank_vision_fallback — retry text-only.")
            stripped = [ChatMessage(m.role, m.content) for m in messages]
            return (
                self.chat(stripped, purpose=purpose, lane=lane, model_override=None),
                False,
            )

    def _ollama_chat_payload(
        self,
        messages: Sequence[ChatMessage],
        *,
        think: bool,
        model: str,
        include_images: bool,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                _ollama_message_dict(m, include_images=include_images)
                for m in messages
            ],
            "stream": stream,
            "think": think,
        }
        keep_alive = (getattr(self._settings, "ollama_keep_alive", "") or "").strip()
        if keep_alive:
            payload["keep_alive"] = keep_alive
        return payload

    def _chat_ollama(
        self,
        messages: Sequence[ChatMessage],
        *,
        think: bool,
        model: str,
        include_images: bool,
    ) -> str:
        base = self._settings.ollama_base_url.rstrip("/")
        url = f"{base}/api/chat"
        payload = self._ollama_chat_payload(
            messages,
            think=think,
            model=model,
            include_images=include_images,
            stream=False,
        )
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            msg = data.get("message") or {}
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
            thinking = msg.get("thinking")
            think_len = len(thinking) if isinstance(thinking, str) else 0
            push_activity_line(
                f"LLM: empty content (thinking_len={think_len}) — visible fallback only."
            )
            return ""

    def _chat_ollama_stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        think: bool,
        model: str,
        include_images: bool,
        on_chunk: Callable[[str], None] | None,
    ) -> str:
        base = self._settings.ollama_base_url.rstrip("/")
        url = f"{base}/api/chat"
        payload = self._ollama_chat_payload(
            messages,
            think=think,
            model=model,
            include_images=include_images,
            stream=True,
        )
        parts: list[str] = []
        with httpx.Client(timeout=self._timeout) as client:
            with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = data.get("message") or {}
                    chunk = msg.get("content")
                    if not isinstance(chunk, str) or not chunk:
                        continue
                    parts.append(chunk)
                    if on_chunk is not None:
                        on_chunk(chunk)
        return "".join(parts).strip()

    def _chat_openai_compatible(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
    ) -> str:
        # OpenAI 호환 API는 think·이미지 미지원 — 텍스트만
        base = self._settings.gemma_api_base_url.rstrip("/")
        url = f"{base}/v1/chat/completions"
        payload = {
            "model": model,
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
