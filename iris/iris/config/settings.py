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


@dataclass(frozen=True)
class Settings:
    """Iris 런타임 설정."""

    gemma_api_base_url: str
    gemma_model_name: str
    gemma_backend: str  # ollama | openai_compatible
    use_local_llm: bool
    use_whisper: bool
    stt_model: str
    tts_engine: str
    tts_speaking_rate: float
    enable_monitoring: bool
    monitor_interval_seconds: int
    store_screenshots: bool
    store_raw_ocr_text: bool
    iris_extension_host: str
    iris_extension_port: int
    iris_extension_token: str
    monitor_stall_seconds: int


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

    return Settings(
        gemma_api_base_url=os.getenv("GEMMA_API_BASE_URL", "http://localhost:11434").rstrip("/"),
        gemma_model_name=os.getenv("GEMMA_MODEL_NAME", "gemma4"),
        gemma_backend=os.getenv("GEMMA_BACKEND", "ollama").strip().lower(),
        use_local_llm=_env_bool("USE_LOCAL_LLM", True),
        use_whisper=_env_bool("USE_WHISPER", True),
        stt_model=os.getenv("STT_MODEL", "small"),
        tts_engine=os.getenv("TTS_ENGINE", "pyttsx3").strip().lower(),
        tts_speaking_rate=_env_float("TTS_SPEAKING_RATE", 1.2),
        enable_monitoring=_env_bool("ENABLE_MONITORING", False),
        monitor_interval_seconds=_env_int("MONITOR_INTERVAL_SECONDS", 3),
        store_screenshots=_env_bool("STORE_SCREENSHOTS", False),
        store_raw_ocr_text=_env_bool("STORE_RAW_OCR_TEXT", False),
        iris_extension_host=os.getenv("IRIS_EXTENSION_HOST", "127.0.0.1"),
        iris_extension_port=_env_int("IRIS_EXTENSION_PORT", 17777),
        iris_extension_token=os.getenv("IRIS_EXTENSION_TOKEN", ""),
        monitor_stall_seconds=_env_int("MONITOR_STALL_SECONDS", 120),
    )
