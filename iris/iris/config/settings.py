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
    gemma_backend: str  # ollama | openai_compatible
    use_local_llm: bool
    use_whisper: bool
    stt_model: str
    # TTS: TTS_PROVIDER 우선 (edge | pyttsx3). 미설정 시 TTS_ENGINE 레거시로 추론.
    tts_provider: str
    tts_voice: str
    tts_rate: str
    tts_pitch: str
    tts_volume: str
    tts_speaking_rate: float
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


def load_settings(env_path: Path | None = None) -> Settings:
    """.env 로드 후 Settings 생성."""
    if env_path is None:
        # 패키지 상위(앱 루트) 우선
        here = Path(__file__).resolve().parent.parent.parent
        env_path = here / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(override=False)

    # Ollama: OLLAMA_BASE_URL 우선, GEMMA_API_BASE_URL은 LM Studio 등 OpenAI 호환용 베이스로 별도 사용
    default_ollama = "http://localhost:11434"
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", default_ollama).rstrip("/")
    gemma_api_env = os.getenv("GEMMA_API_BASE_URL")
    gemma_api_base_url = (gemma_api_env or ollama_base_url).rstrip("/")

    return Settings(
        ollama_base_url=ollama_base_url,
        gemma_api_base_url=gemma_api_base_url,
        gemma_model_name=os.getenv("GEMMA_MODEL_NAME", "gemma4:e2b"),
        gemma_backend=os.getenv("GEMMA_BACKEND", "ollama").strip().lower(),
        use_local_llm=_env_bool("USE_LOCAL_LLM", True),
        use_whisper=_env_bool("USE_WHISPER", True),
        stt_model=os.getenv("STT_MODEL", "small"),
        tts_provider=_resolve_tts_provider(),
        tts_voice=os.getenv("TTS_VOICE", "ko-KR-SunHiNeural").strip(),
        tts_rate=os.getenv("TTS_RATE", "-5%").strip(),
        tts_pitch=os.getenv("TTS_PITCH", "+0Hz").strip(),
        tts_volume=os.getenv("TTS_VOLUME", "+0%").strip(),
        tts_speaking_rate=_env_float("TTS_SPEAKING_RATE", 1.2),
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
    )
