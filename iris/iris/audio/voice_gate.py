"""웨이크워드 기반 음성 명령 게이트 (STT 오인식 fuzzy 매칭)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


# Whisper가 「아이리스」를 잘못 쓰는 패턴 — 호출어로 인정
_FUZZY_WAKE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"아\s*이\s*리\s*스", re.IGNORECASE), "아이리스"),
    (re.compile(r"하\s*이\s*리\s*스", re.IGNORECASE), "아이리스"),
    (re.compile(r"아\s*이\s*리", re.IGNORECASE), "아이리스"),
    (re.compile(r"이\s*리\s*스", re.IGNORECASE), "아이리스"),
    (re.compile(r"\biris\b", re.IGNORECASE), "iris"),
    (re.compile(r"이리스", re.IGNORECASE), "이리스"),
]

# 호출어만 짧게 말했을 때 STT 단편 — follow-up 대기용
_PARTIAL_WAKE_ONLY = re.compile(
    r"^(아이리스|아이리|아이|이리스|리스|iris|이리스|하이리스|아이\s*리스|아)$",
    re.IGNORECASE,
)


def find_wake_match(text: str, wake_words: tuple[str, ...]) -> str | None:
    """텍스트에서 호출어(정확·fuzzy) 매칭. 매칭 시 canonical 이름 반환."""
    clean = _normalize(text)
    if not clean:
        return None
    low = clean.lower()
    for w in wake_words:
        if w.lower() in low:
            return w
    for pat, canonical in _FUZZY_WAKE_PATTERNS:
        if pat.search(clean):
            return canonical
    if _PARTIAL_WAKE_ONLY.match(clean):
        return wake_words[0] if wake_words else "아이리스"
    return None


def strip_wake_prefix(text: str, matched: str) -> str:
    """매칭된 호출어를 제거하고 명령 본문만 남김."""
    clean = _normalize(text)
    low = clean.lower()
    mlow = matched.lower()
    if mlow in low:
        out = re.sub(re.escape(matched), "", clean, count=1, flags=re.IGNORECASE)
        return _normalize(out.strip(" ,.!?。、·"))
    for pat, canonical in _FUZZY_WAKE_PATTERNS:
        if pat.search(clean):
            out = pat.sub("", clean, count=1)
            return _normalize(out.strip(" ,.!?。、·"))
    return ""


@dataclass(frozen=True)
class VoiceGateResult:
    accepted: bool
    command_text: str
    prompt_only: bool = False
    reject_reason: str = ""


class VoiceCommandGate:
    """아이리스 호출어가 있을 때만 음성 명령을 통과시킨다."""

    def __init__(
        self,
        *,
        wake_words: tuple[str, ...] = ("아이리스", "iris", "이리스"),
        require_wake_word: bool = True,
        followup_seconds: float = 8.0,
    ) -> None:
        self._wake_words = tuple(w for w in wake_words if w.strip())
        self._require_wake_word = require_wake_word
        self._followup_seconds = max(0.0, followup_seconds)
        self._awake_until = 0.0
        self._followup_paused = False
        self._followup_remaining = 0.0

    def reset(self) -> None:
        self._awake_until = 0.0
        self._followup_paused = False
        self._followup_remaining = 0.0

    def pause_followup_timer(self) -> None:
        """TTS/처리 중 follow-up 타이머 정지 — 남은 시간 보존."""
        now = time.time()
        if now < self._awake_until and not self._followup_paused:
            self._followup_remaining = self._awake_until - now
            self._followup_paused = True

    def resume_followup_timer(self) -> None:
        """TTS 종료 후 follow-up 윈도우 복원."""
        if self._followup_paused and self._followup_remaining > 0:
            self._awake_until = time.time() + self._followup_remaining
        self._followup_paused = False
        self._followup_remaining = 0.0

    def filter(self, text: str) -> VoiceGateResult:
        clean = _normalize(text)
        if not clean:
            return VoiceGateResult(False, "", reject_reason="empty")
        if not self._require_wake_word:
            return VoiceGateResult(True, clean)

        now = time.time()
        matched = find_wake_match(clean, self._wake_words)
        if matched:
            self._awake_until = now + self._followup_seconds
            command = strip_wake_prefix(clean, matched)
            if command:
                return VoiceGateResult(True, command)
            return VoiceGateResult(True, "", prompt_only=True)

        if not self._followup_paused and now <= self._awake_until:
            return VoiceGateResult(True, clean)

        return VoiceGateResult(
            False,
            "",
            reject_reason="wake_word",
        )
