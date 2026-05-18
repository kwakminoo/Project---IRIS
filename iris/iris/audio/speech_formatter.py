"""채팅용 원문과 음성 출력용 문장 분리·구어체 변환."""

from __future__ import annotations

import re
from typing import Final

from iris.core.state_machine import AppState

# 문어체 → 구어체 (부분 일치 순서: 긴 패턴 우선)
_PHRASE_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (
    (r"요청하신 작업을 수행하겠습니다\.?", "바로 준비할게요."),
    (r"네,\s*요청하신 작업을 수행하겠습니다\.?", "좋아요. 바로 준비할게요."),
    (r"최신\s*정보가\s*필요한\s*질문입니다\.?\s*웹\s*검색을\s*수행하겠습니다\.?", "이건 최신 정보가 필요해요. 검색해서 정리해드릴게요."),
    (r"작업을\s*수행하겠습니다\.?", "진행할게요."),
    (r"현재\s*등록된\s*모니터링\s*대상이\s*없습니다\.?", "아직 감시 중인 작업은 없어요. 작업을 시작하면 제가 같이 확인할게요."),
    (r"모니터링\s*대상이\s*없습니다\.?", "감시 중인 항목은 아직 없어요."),
    (r"사용자의\s*명령을\s*처리하는\s*중입니다\.?", "잠깐만요. 지금 확인하고 있어요."),
    (r"처리하는\s*중입니다\.?", "지금 처리 중이에요."),
    (r"확인하는\s*중입니다\.?", "잠깐만요. 확인해볼게요."),
    (r"오류가\s*발생했습니다\.?", "음, 여기서 문제가 생긴 것 같아요. 다시 확인해볼게요."),
    (r"에러가\s*발생했습니다\.?", "문제가 생긴 것 같아요. 잠깐만요."),
    (r"실패했습니다\.?", "잘 안 됐어요. 다시 볼게요."),
    (r"알\s*수\s*없습니다\.?", "잘 모르겠어요."),
    (r"이해했습니다\.?", "알겠어요."),
    (r"감사합니다\.?", "고마워요."),
    (r"어떤 작업을 실행할까요\?", "뭘 함께할까요?"),
)


def _apply_phrase_map(text: str) -> str:
    t = text.strip()
    for pattern, repl in _PHRASE_REPLACEMENTS:
        t2, n = re.subn(pattern, repl, t, flags=re.IGNORECASE)
        if n:
            t = t2
    return t


def _soften_formal_korean(text: str) -> str:
    """남은 경어체를 과하지 않게 구어체에 가깝게."""
    t = text
    t = re.sub(r"습니다\.", "어요.", t)
    t = re.sub(r"습니다\b", "어요", t)
    t = re.sub(r"입니다\.", "이에요.", t)
    t = re.sub(r"입니다\b", "이에요", t)
    t = re.sub(r"하겠습니다\.", "할게요.", t)
    t = re.sub(r"하겠습니다\b", "할게요", t)
    return t


def _split_sentences(text: str) -> list[str]:
    """문장 단위 분리 (한국어 마침표·물음표 등)."""
    t = text.strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?。])\s+", t)
    return [p.strip() for p in parts if p.strip()]


def _limit_sentences(text: str, max_sentences: int = 3, max_chars: int = 320) -> str:
    """음성용으로 길이·문장 수 제한."""
    sents = _split_sentences(text)
    if not sents:
        return (text or "").strip()[:max_chars]
    picked = sents[:max_sentences]
    out = " ".join(picked)
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out


def _strip_non_speech_markup(text: str) -> str:
    """LLM/도구 메타 출력, 주석, SSML 잔여물을 음성 출력에서 제거한다."""
    t = text.strip()
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"(?is)~~~[\s\S]*?~~~", " ", t)
    t = re.sub(r"(?is)<(?:speak|voice|prosody|break|mstts:[^>]+)[^>]*>", " ", t)
    t = re.sub(r"(?is)</(?:speak|voice|prosody|mstts:[^>]+)>", " ", t)
    t = re.sub(r"(?is)<[^>]{1,80}>", " ", t)
    t = re.sub(r"(?im)^\s*//.*$", " ", t)
    t = re.sub(r"(?m)(?<!https:)//[^\n\r]*", " ", t)
    t = re.sub(r"(?im)^\s*#.*$", " ", t)
    t = re.sub(
        r"(?im)^\s*(?:tool|action|observation|json|assistant|system|speech|tts)\s*[:：].*$",
        " ",
        t,
    )
    t = re.sub(r"(?is)\{[\s\S]*?(?:\"tool\"|\"action\"|\"steps\"|\"intent\"|\"speak\")[\s\S]*?\}", " ", t)
    t = re.sub(r"(?im)^\s*(?:speak|스픽)\s*[:：-]?\s*", "", t)
    t = re.sub(r"\b(?:speak|스픽)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"(?im)^\s*[/\\<>]+\s*$", " ", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _tone_adjust(text: str, tone: AppState, *, max_sentences: int = 3) -> str:
    """상태별 말투·짧은 반응."""
    base = text.strip()
    cap = max(1, min(max_sentences, 5))
    if not base:
        return "네."

    if tone is AppState.LISTENING:
        if len(base) > 48:
            return _limit_sentences(base, max_sentences=1, max_chars=48)
        return base

    if tone is AppState.PROCESSING:
        if any(k in base for k in ("잠깐", "확인", "처리")):
            return _limit_sentences(base, max_sentences=min(2, cap), max_chars=200)
        return _limit_sentences("잠깐만요. " + base, max_sentences=cap, max_chars=320)

    if tone is AppState.EXECUTING:
        if not any(k in base for k in ("실행", "진행", "할게", "시작")):
            return _limit_sentences("좋아요. " + base, max_sentences=cap, max_chars=320)
        return _limit_sentences(base, max_sentences=cap, max_chars=320)

    if tone is AppState.ALERTING:
        if not any(k in base for k in ("멈춘", "문제", "확인", "같")):
            return _limit_sentences("확인해보니, " + base, max_sentences=cap, max_chars=320)
        return _limit_sentences(base, max_sentences=cap, max_chars=320)

    # IDLE, RESPONDING, MONITORING, ERROR 등 — 차분한 구어체
    return _limit_sentences(base, max_sentences=cap, max_chars=320)


def format_speech(text: str, tone: AppState, *, max_sentences: int = 3) -> str:
    """
    채팅에 표시된 원문을 음성용 짧은 구어체로 변환.

    - 최대 max_sentences문장 (기본 2~3)
    - 문장 사이 짧은 쉼: 줄바꿈(엔진이 자연스러운 호흡으로 읽기 쉬움)
    """
    raw = (text or "").strip()
    raw = re.sub(r"^Iris:\s*", "", raw, flags=re.IGNORECASE)
    raw = _strip_non_speech_markup(raw)
    if not raw:
        return "네, 말씀해 주세요."

    mapped = _apply_phrase_map(raw)
    softened = _soften_formal_korean(mapped)
    toned = _tone_adjust(softened, tone, max_sentences=max_sentences)

    sents = _split_sentences(toned)
    cap = max(1, min(max_sentences, 5))
    if len(sents) <= 1:
        return toned.strip()

    # 문장 사이 짧은 pause 느낌
    return "\n".join(sents[:cap])


def format_system_info_spoken(text: str) -> str:
    """get_system_info 요약 등 하드웨어 안내 → TTS용 짧은 구어체 (EXECUTING 톤)."""
    raw = (text or "").strip()
    if not raw:
        return "네, 말씀해 주세요."
    return format_speech(raw, AppState.EXECUTING, max_sentences=2)


def infer_speech_tone(*, from_llm: bool, reply_text: str) -> AppState:
    """
    음성 말투 추론.

    - LLM 일반 답변: 차분한 IDLE 톤
    - 규칙 기반 즉시 답변: 문구 패턴으로 EXECUTING / ALERTING 등
    """
    t = reply_text.strip()
    if not t:
        return AppState.IDLE

    if from_llm:
        if any(k in t for k in ("오류", "실패", "에러", "error", "문제가")):
            return AppState.ALERTING
        return AppState.IDLE

    tl = t.lower()
    if any(k in t for k in ("오류", "실패", "에러", "문제가 발생", "할 수 없")):
        return AppState.ALERTING
    if "어떤 작업" in t and "?" in t:
        return AppState.LISTENING
    if any(
        k in t
        for k in (
            "실행",
            "시작했",
            "완료했",
            "배치",
            "레이아웃",
            "앱을 켰",
            "실행했",
        )
    ):
        return AppState.EXECUTING
    if any(k in t for k in ("잠깐", "확인 중", "처리 중", "기다려")):
        return AppState.PROCESSING
    if len(t) < 28 and "\n" not in t:
        return AppState.LISTENING

    if "monitor" in tl or "모니터" in t:
        if "멈춤" in t or "stall" in tl or "주의" in t:
            return AppState.ALERTING

    return AppState.IDLE
