"""환경 변수 기반 설정 로드."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


class RouterMode(str, Enum):
    """라우터 운영 모드 — 단일 설정 객체로 정규화."""

    HYBRID = "hybrid"
    FRONTIER_FIRST = "frontier_first"
    UNIFIED_ONLY = "unified_only"


class TextTtsSyncMode(str, Enum):
    FAST = "fast"
    SYNCHRONIZED = "synchronized"


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
    """TTS_PROVIDER 우선, 없으면 TTS_ENGINE 레거시, 둘 다 없으면 supertonic."""
    explicit = os.getenv("TTS_PROVIDER")
    if explicit is not None and explicit.strip():
        return explicit.strip().lower()
    legacy = os.getenv("TTS_ENGINE")
    if legacy is not None and legacy.strip():
        return "pyttsx3" if legacy.strip().lower() == "pyttsx3" else "edge"
    return "supertonic"


@dataclass(frozen=True)
class Settings:
    """Iris 런타임 설정."""

    ollama_base_url: str
    ollama_keep_alive: str  # Ollama keep_alive (비우면 payload 생략)
    gemma_api_base_url: str
    gemma_model_name: str
    ai_model_names: tuple[str, ...]
    gemma_backend: str  # ollama | openai_compatible
    llm_timeout_seconds: float
    use_local_llm: bool
    use_whisper: bool
    stt_model: str
    stt_device: str  # auto | cpu | cuda
    stt_compute_type: str  # auto | int8 | float16
    stt_vad_filter: bool  # False 권장: 앞단 RMS VAD와 중복 방지
    stt_beam_size: int
    stt_initial_prompt: str  # 비어 있으면 호출어 기반 자동 생성
    stt_condition_on_previous_text: bool
    stt_no_speech_threshold: float
    stt_min_avg_logprob: float
    # TTS: TTS_PROVIDER (supertonic | xtts | edge | pyttsx3). 미설정 시 TTS_ENGINE 레거시로 추론.
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
    supertonic_voice: str
    supertonic_language: str
    supertonic_total_steps: int
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
    # Tier 4 외부 에이전트 — 로컬 Computer Use 실패 시에만(기본 비활성)
    external_agent_backend: str  # none | openclaw | hermes
    external_agent_fallback_enabled: bool
    external_agent_verify_perception: bool  # 성공 주장 시 1회 perceive_desktop 검증
    hermes_cli_path: str
    # Barge-in / 상시 음성
    barge_in_enabled: bool
    barge_in_grace_ms: int
    barge_in_rms_multiplier: float
    voice_resume_delay_ms: int
    voice_vad_auto_calibrate: bool
    voice_speech_rms_multiplier: float
    voice_silence_rms_multiplier: float
    always_listen_speech_rms_manual: bool
    tts_processing_filler: bool
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
    # TurnCoordinator 기본 경로 (Computer Use PAV). UI는 IRIS_MULTI_AGENT와 무관하게 Coordinator 사용
    multi_agent_enabled: bool
    # Deterministic chat/action fast path (LLM 생략)
    chat_fast_path_enabled: bool
    # Frontier — 복합 요청 오케스트레이터 (hybrid 모드에서만 조건부 호출)
    frontier_enabled: bool
    frontier_complex_only: bool
    frontier_min_confidence: float
    frontier_complexity_threshold: float
    # Unified LLM Router (자연어 전체 → intent/lane/slots). false면 llm_intent_router 또는 규칙만
    unified_llm_router_enabled: bool
    # LLM Intent Router (Gemma 1회 JSON → lane/goal). unified 비활성 시 사용
    llm_intent_router_enabled: bool
    # LLM 승인 분류 (pending_cu·자동화 후속). false면 규칙 is_rule_approval만
    llm_approval_enabled: bool
    # 라우터 모드·계측·프롬프트 경량화
    router_mode: str
    router_telemetry_enabled: bool
    router_history_turns: int
    router_app_candidate_limit: int
    text_tts_sync_mode: str
    # 웹 URL 열기: chrome | edge | firefox | system
    default_web_browser: str
    # Computer Use Phase B: UIA / VLM 하이브리드 인식
    computer_use_uia_enabled: bool
    computer_use_vlm_enabled: bool
    computer_use_vlm_on_verify: bool  # checkpoint verify·repair VLM
    computer_use_vlm_on_planner: bool  # full/step planner VLM
    computer_use_vision_model: str  # 비우면 gemma_model_name
    computer_use_input_notify_delay_seconds: float  # 키보드·마우스 충돌 안내 후 대기
    computer_use_full_plan_enabled: bool  # 초기 Perceive 후 전체 plans[] 1회 작성
    type_input_verify_enabled: bool  # typewrite·unicode 경로만 검증
    type_input_max_retries: int  # 검증 불일치 시 재시도 상한 (0~1)
    type_input_visible_interval: float  # 글자 간격(초) — 보이는 입력
    # Phase 3: 멀티턴 프리셋 매칭에 Gemma 1회 (실패 시 modes/* regex 폴백)
    phase3_mode_preset_llm: bool
    # Ollama think: off | default | on (IRIS_THINKING_MODE)
    thinking_mode: str
    # DIALOGUE_CHAT 전용 최근 턴 수 (1턴=user+assistant 2메시지)
    dialogue_history_turns: int
    # Media Ranker — 창 스크린샷 멀티모달 (DB·디스크 저장 없음, HTTP body만)
    media_ranker_use_screenshot: bool
    media_ranker_vision_model: str  # 비어 있으면 gemma_model_name
    # 내장 IDE — Theia workspace 루트 (비어 있으면 저장소 루트)
    ide_workspace_path: str


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
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "").strip(),
        gemma_api_base_url=gemma_api_base_url,
        gemma_model_name=model_name,
        ai_model_names=model_names or (model_name,),
        gemma_backend=os.getenv("GEMMA_BACKEND", "ollama").strip().lower(),
        llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 60.0),
        use_local_llm=_env_bool("USE_LOCAL_LLM", True),
        use_whisper=_env_bool("USE_WHISPER", True),
        stt_model=os.getenv("STT_MODEL", "medium"),
        stt_device=os.getenv("STT_DEVICE", "auto").strip().lower(),
        stt_compute_type=os.getenv("STT_COMPUTE_TYPE", "auto").strip().lower(),
        stt_vad_filter=_env_bool("STT_VAD_FILTER", False),
        stt_beam_size=_env_int("STT_BEAM_SIZE", 5),
        stt_initial_prompt=os.getenv("STT_INITIAL_PROMPT", "").strip(),
        stt_condition_on_previous_text=_env_bool("STT_CONDITION_ON_PREVIOUS_TEXT", False),
        stt_no_speech_threshold=_env_float("STT_NO_SPEECH_THRESHOLD", 0.6),
        stt_min_avg_logprob=_env_float("STT_MIN_AVG_LOGPROB", -1.0),
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
        supertonic_voice=os.getenv("SUPERTONIC_VOICE", "Lily").strip(),
        supertonic_language=os.getenv("SUPERTONIC_LANGUAGE", "ko").strip(),
        supertonic_total_steps=_env_int("SUPERTONIC_TOTAL_STEPS", 8),
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
        external_agent_backend=os.getenv("EXTERNAL_AGENT_BACKEND", "none").strip().lower(),
        external_agent_fallback_enabled=_env_bool("EXTERNAL_AGENT_FALLBACK_ENABLED", False),
        external_agent_verify_perception=_env_bool("EXTERNAL_AGENT_VERIFY_PERCEPTION", False),
        hermes_cli_path=os.getenv("HERMES_CLI_PATH", "hermes").strip(),
        barge_in_enabled=_env_bool("BARGE_IN_ENABLED", False),
        barge_in_grace_ms=_env_int("BARGE_IN_GRACE_MS", 450),
        barge_in_rms_multiplier=_env_float("BARGE_IN_RMS_MULTIPLIER", 3.0),
        voice_resume_delay_ms=_env_int("VOICE_RESUME_DELAY_MS", 250),
        voice_vad_auto_calibrate=_env_bool("VOICE_VAD_AUTO_CALIBRATE", True),
        voice_speech_rms_multiplier=_env_float("VOICE_SPEECH_RMS_MULTIPLIER", 2.5),
        voice_silence_rms_multiplier=_env_float("VOICE_SILENCE_RMS_MULTIPLIER", 1.3),
        always_listen_speech_rms_manual=os.getenv("ALWAYS_LISTEN_SPEECH_RMS") is not None,
        tts_processing_filler=_env_bool("TTS_PROCESSING_FILLER", False),
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
        multi_agent_enabled=_env_bool("IRIS_MULTI_AGENT", True),
        chat_fast_path_enabled=_env_bool("IRIS_CHAT_FAST_PATH", True),
        frontier_enabled=_env_bool("IRIS_FRONTIER_ENABLED", True),
        frontier_complex_only=_env_bool("IRIS_FRONTIER_COMPLEX_ONLY", True),
        frontier_min_confidence=_env_float("IRIS_FRONTIER_MIN_CONFIDENCE", 0.65),
        frontier_complexity_threshold=_env_float(
            "IRIS_FRONTIER_COMPLEXITY_THRESHOLD", 0.70
        ),
        unified_llm_router_enabled=_env_bool("IRIS_UNIFIED_LLM_ROUTER", True),
        llm_intent_router_enabled=_env_bool("IRIS_LLM_INTENT_ROUTER", True),
        llm_approval_enabled=_env_bool("IRIS_LLM_APPROVAL", True),
        router_mode=os.getenv("IRIS_ROUTER_MODE", "hybrid").strip().lower(),
        router_telemetry_enabled=_env_bool("IRIS_ROUTER_TELEMETRY", True),
        router_history_turns=max(0, _env_int("IRIS_ROUTER_HISTORY_TURNS", 2)),
        router_app_candidate_limit=max(1, _env_int("IRIS_ROUTER_APP_CANDIDATE_LIMIT", 5)),
        text_tts_sync_mode=os.getenv("IRIS_TEXT_TTS_SYNC_MODE", "fast").strip().lower(),
        default_web_browser=os.getenv("DEFAULT_WEB_BROWSER", "chrome").strip().lower(),
        computer_use_uia_enabled=_env_bool("COMPUTER_USE_UIA_ENABLED", True),
        computer_use_vlm_enabled=_env_bool("COMPUTER_USE_VLM_ENABLED", False),
        computer_use_vlm_on_verify=_env_bool("COMPUTER_USE_VLM_ON_VERIFY", True),
        computer_use_vlm_on_planner=_env_bool("COMPUTER_USE_VLM_ON_PLANNER", False),
        computer_use_vision_model=os.getenv("COMPUTER_USE_VISION_MODEL", "").strip(),
        computer_use_input_notify_delay_seconds=_env_float(
            "COMPUTER_USE_INPUT_NOTIFY_DELAY_SECONDS", 2.0
        ),
        computer_use_full_plan_enabled=_env_bool("COMPUTER_USE_FULL_PLAN_ENABLED", True),
        type_input_verify_enabled=_env_bool("TYPE_INPUT_VERIFY_ENABLED", True),
        type_input_max_retries=min(
            1, max(0, _env_int("TYPE_INPUT_MAX_RETRIES", 1))
        ),
        type_input_visible_interval=_env_float("TYPE_INPUT_VISIBLE_INTERVAL", 0.03),
        phase3_mode_preset_llm=_env_bool("IRIS_PHASE3_MODE_PRESET_LLM", True),
        thinking_mode=_normalize_thinking_mode_env(
            os.getenv("IRIS_THINKING_MODE", "default")
        ),
        dialogue_history_turns=max(0, _env_int("DIALOGUE_HISTORY_TURNS", 4)),
        media_ranker_use_screenshot=_env_bool(
            "IRIS_MEDIA_RANKER_USE_SCREENSHOT", True
        ),
        media_ranker_vision_model=os.getenv(
            "IRIS_MEDIA_RANKER_VISION_MODEL", ""
        ).strip(),
        ide_workspace_path=os.getenv("IRIS_IDE_WORKSPACE_PATH", "").strip(),
    )


def _normalize_thinking_mode_env(raw: str) -> str:
    """환경 변수 → off | default | on."""
    from iris.ai.thinking_policy import normalize_thinking_mode

    return normalize_thinking_mode(raw)


def get_router_mode(settings: Settings) -> RouterMode:
    raw = getattr(settings, "router_mode", "hybrid")
    if isinstance(raw, RouterMode):
        return raw
    try:
        return RouterMode(str(raw).strip().lower())
    except ValueError:
        return RouterMode.HYBRID


def get_text_tts_sync_mode(settings: Settings) -> TextTtsSyncMode:
    raw = getattr(settings, "text_tts_sync_mode", "fast")
    if isinstance(raw, TextTtsSyncMode):
        return raw
    try:
        return TextTtsSyncMode(str(raw).strip().lower())
    except ValueError:
        return TextTtsSyncMode.FAST
