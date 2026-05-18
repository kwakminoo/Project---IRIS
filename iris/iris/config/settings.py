"""환경 변수 기반 설정 로드."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_optional_int(key: str) -> int | None:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _resolve_tts_provider() -> str:
    """TTS_PROVIDER 우선, 없으면 TTS_ENGINE 레거시, 둘 다 없으면 edge."""
    explicit = os.getenv("TTS_PROVIDER")
    if explicit is not None and explicit.strip():
        return explicit.strip().lower()
    legacy = os.getenv("TTS_ENGINE")
    if legacy is not None and legacy.strip():
        return "pyttsx3" if legacy.strip().lower() == "pyttsx3" else "edge"
    return "edge"


@dataclass(frozen=True)
class Settings:
    """Iris 런타임 설정."""

    ollama_base_url: str
    gemma_api_base_url: str
    gemma_model_name: str
    ai_model_names: tuple[str, ...]
    gemma_backend: str  # ollama | openai_compatible
    use_local_llm: bool
    use_whisper: bool
    stt_model: str
    stt_device: str  # auto | cpu | cuda
    stt_compute_type: str  # auto | int8 | float16
    stt_vad_filter: bool  # False 권장: 앞단 RMS VAD와 중복 방지
    stt_beam_size: int
    stt_initial_prompt: str  # 비어 있으면 호출어 기반 자동 생성
    # TTS: TTS_PROVIDER (xtts | edge | pyttsx3). 미설정 시 TTS_ENGINE 레거시로 추론.
    tts_provider: str
    tts_fallback_provider: str
    tts_voice: str
    tts_rate: str
    tts_pitch: str
    tts_volume: str
    tts_speaking_rate: float
    tts_voice_preset: str
    tts_enable_speech_formatter: bool
    tts_enable_voice_fx: bool
    tts_max_spoken_sentences: int
    # XTTS-v2 (선택, requirements-tts.txt)
    xtts_model_name: str
    xtts_language: str
    xtts_reference_wav: str
    xtts_device: str
    xtts_speed: float
    xtts_enable_cache: bool
    xtts_cache_dir: str
    enable_monitoring: bool
    monitor_interval_seconds: int
    store_screenshots: bool
    store_raw_ocr_text: bool
    iris_extension_host: str
    iris_extension_port: int
    iris_extension_token: str
    monitor_stall_seconds: int
    # OpenClaw — 내부 Action Backend (사용자 UI에는 노출 최소화)
    openclaw_enabled: bool
    openclaw_mode: str
    openclaw_cli_path: str
    openclaw_session_id: str
    openclaw_timeout_seconds: int
    # Barge-in / 상시 음성
    barge_in_enabled: bool
    always_listen_enabled: bool
    always_listen_sample_rate: int
    always_listen_speech_rms: float
    always_listen_silence_rms: float
    always_listen_silence_ms: int
    always_listen_min_speech_ms: int
    always_listen_max_seconds: float
    always_listen_input_device: int | None
    voice_require_wake_word: bool
    voice_wake_words: tuple[str, ...]
    voice_followup_seconds: float
    # 멀티-역할 파이프라인 (Router·Dialogue·Coordinator)
    multi_agent_enabled: bool


def load_settings(env_path: Path | None = None) -> Settings:
    """.env 로드 후 Settings 생성."""
    if env_path is None:
        # 패키지 상위(앱 루트) 우선
        here = Path(__file__).resolve().parent.parent.parent
        env_path = here / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=False)

    # Ollama: OLLAMA_BASE_URL 우선, GEMMA_API_BASE_URL은 LM Studio 등 OpenAI 호환용 베이스로 별도 사용
    default_ollama = "http://localhost:11434"
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", default_ollama).rstrip("/")
    gemma_api_env = os.getenv("GEMMA_API_BASE_URL")
    gemma_api_base_url = (gemma_api_env or ollama_base_url).rstrip("/")
    model_name = os.getenv("GEMMA_MODEL_NAME", "gemma4:e2b").strip()
    model_names = tuple(
        dict.fromkeys(
            [model_name]
            + [
                m.strip()
                for m in os.getenv("AI_MODEL_NAMES", model_name).split(",")
                if m.strip()
            ]
        )
    )

    return Settings(
        ollama_base_url=ollama_base_url,
        gemma_api_base_url=gemma_api_base_url,
        gemma_model_name=model_name,
        ai_model_names=model_names or (model_name,),
        gemma_backend=os.getenv("GEMMA_BACKEND", "ollama").strip().lower(),
        use_local_llm=_env_bool("USE_LOCAL_LLM", True),
        use_whisper=_env_bool("USE_WHISPER", True),
        stt_model=os.getenv("STT_MODEL", "medium"),
        stt_device=os.getenv("STT_DEVICE", "auto").strip().lower(),
        stt_compute_type=os.getenv("STT_COMPUTE_TYPE", "auto").strip().lower(),
        stt_vad_filter=_env_bool("STT_VAD_FILTER", False),
        stt_beam_size=_env_int("STT_BEAM_SIZE", 5),
        stt_initial_prompt=os.getenv("STT_INITIAL_PROMPT", "").strip(),
        tts_provider=_resolve_tts_provider(),
        tts_fallback_provider=os.getenv("TTS_FALLBACK_PROVIDER", "edge").strip().lower(),
        tts_voice=os.getenv("TTS_VOICE", "ko-KR-SunHiNeural").strip(),
        tts_rate=os.getenv("TTS_RATE", "-5%").strip(),
        tts_pitch=os.getenv("TTS_PITCH", "+0Hz").strip(),
        tts_volume=os.getenv("TTS_VOLUME", "+0%").strip(),
        tts_speaking_rate=_env_float("TTS_SPEAKING_RATE", 1.2),
        tts_voice_preset=os.getenv("TTS_VOICE_PRESET", "iris_default").strip(),
        tts_enable_speech_formatter=_env_bool("TTS_ENABLE_SPEECH_FORMATTER", True),
        tts_enable_voice_fx=_env_bool("TTS_ENABLE_VOICE_FX", True),
        tts_max_spoken_sentences=_env_int("TTS_MAX_SPOKEN_SENTENCES", 3),
        xtts_model_name=os.getenv(
            "XTTS_MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2"
        ).strip(),
        xtts_language=os.getenv("XTTS_LANGUAGE", "ko").strip(),
        xtts_reference_wav=os.getenv("XTTS_REFERENCE_WAV", "assets/voices/iris_reference.wav").strip(),
        xtts_device=os.getenv("XTTS_DEVICE", "auto").strip().lower(),
        xtts_speed=_env_float("XTTS_SPEED", 1.0),
        xtts_enable_cache=_env_bool("XTTS_ENABLE_CACHE", True),
        xtts_cache_dir=os.getenv("XTTS_CACHE_DIR", ".cache/tts").strip(),
        enable_monitoring=_env_bool("ENABLE_MONITORING", False),
        monitor_interval_seconds=_env_int("MONITOR_INTERVAL_SECONDS", 3),
        store_screenshots=_env_bool("STORE_SCREENSHOTS", False),
        store_raw_ocr_text=_env_bool("STORE_RAW_OCR_TEXT", False),
        iris_extension_host=os.getenv("IRIS_EXTENSION_HOST", "127.0.0.1"),
        iris_extension_port=_env_int("IRIS_EXTENSION_PORT", 17777),
        iris_extension_token=os.getenv("IRIS_EXTENSION_TOKEN", ""),
        monitor_stall_seconds=_env_int("MONITOR_STALL_SECONDS", 120),
        openclaw_enabled=_env_bool("OPENCLAW_ENABLED", False),
        openclaw_mode=os.getenv("OPENCLAW_MODE", "action_backend").strip().lower(),
        openclaw_cli_path=os.getenv("OPENCLAW_CLI_PATH", "openclaw").strip(),
        openclaw_session_id=os.getenv("OPENCLAW_SESSION_ID", "iris-action").strip(),
        openclaw_timeout_seconds=_env_int("OPENCLAW_TIMEOUT_SECONDS", 90),
        barge_in_enabled=_env_bool("BARGE_IN_ENABLED", False),
        always_listen_enabled=_env_bool("ALWAYS_LISTEN_ENABLED", True),
        always_listen_sample_rate=_env_int("ALWAYS_LISTEN_SAMPLE_RATE", 16000),
        always_listen_speech_rms=_env_float("ALWAYS_LISTEN_SPEECH_RMS", 0.018),
        always_listen_silence_rms=_env_float("ALWAYS_LISTEN_SILENCE_RMS", 0.009),
        always_listen_silence_ms=_env_int("ALWAYS_LISTEN_SILENCE_MS", 300),
        always_listen_min_speech_ms=_env_int("ALWAYS_LISTEN_MIN_SPEECH_MS", 350),
        always_listen_max_seconds=_env_float("ALWAYS_LISTEN_MAX_SECONDS", 18.0),
        always_listen_input_device=_env_optional_int("ALWAYS_LISTEN_INPUT_DEVICE"),
        voice_require_wake_word=_env_bool("VOICE_REQUIRE_WAKE_WORD", True),
        voice_wake_words=tuple(
            w.strip()
            for w in os.getenv("VOICE_WAKE_WORDS", "아이리스,iris,이리스").split(",")
            if w.strip()
        ),
        voice_followup_seconds=_env_float("VOICE_FOLLOWUP_SECONDS", 8.0),
        multi_agent_enabled=_env_bool("IRIS_MULTI_AGENT", False),
    )
