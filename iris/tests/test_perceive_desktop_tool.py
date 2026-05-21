"""perceive_desktop·build_perception 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iris.automation.tool_types import AutomationToolContext
from iris.automation.tools import PerceiveDesktopTool, build_perception_observation
from iris.config.settings import Settings


def _settings(uia: bool = True, vlm: bool = False) -> Settings:
    return Settings(
        ollama_base_url="http://localhost:11434",
        gemma_api_base_url="http://localhost:11434",
        gemma_model_name="test",
        ai_model_names=("test",),
        gemma_backend="ollama",
        use_local_llm=True,
        use_whisper=False,
        stt_model="medium",
        stt_device="cpu",
        stt_compute_type="int8",
        stt_vad_filter=False,
        stt_beam_size=5,
        stt_initial_prompt="",
        tts_provider="edge",
        tts_fallback_provider="edge",
        tts_voice="ko-KR-SunHiNeural",
        tts_rate="-5%",
        tts_pitch="+0Hz",
        tts_volume="+0%",
        tts_speaking_rate=1.0,
        tts_voice_preset="iris_default",
        tts_enable_speech_formatter=True,
        tts_enable_voice_fx=True,
        tts_max_spoken_sentences=3,
        xtts_model_name="x",
        xtts_language="ko",
        xtts_reference_wav="",
        xtts_device="cpu",
        xtts_speed=1.0,
        xtts_enable_cache=False,
        xtts_cache_dir=".cache",
        enable_monitoring=False,
        monitor_interval_seconds=3,
        store_screenshots=False,
        store_raw_ocr_text=False,
        iris_extension_host="127.0.0.1",
        iris_extension_port=17777,
        iris_extension_token="",
        monitor_stall_seconds=120,
        openclaw_enabled=False,
        openclaw_mode="action_backend",
        openclaw_cli_path="openclaw",
        openclaw_session_id="iris",
        openclaw_timeout_seconds=90,
        external_agent_backend="none",
        external_agent_fallback_enabled=False,
        external_agent_verify_perception=False,
        hermes_cli_path="hermes",
        barge_in_enabled=False,
        always_listen_enabled=False,
        always_listen_sample_rate=16000,
        always_listen_speech_rms=0.018,
        always_listen_silence_rms=0.009,
        always_listen_silence_ms=300,
        always_listen_min_speech_ms=350,
        always_listen_max_seconds=18.0,
        always_listen_input_device=None,
        voice_require_wake_word=True,
        voice_wake_words=("iris",),
        voice_followup_seconds=8.0,
        multi_agent_enabled=False,
        chat_fast_path_enabled=True,
        unified_llm_router_enabled=True,
        llm_intent_router_enabled=True,
        llm_approval_enabled=True,
        default_web_browser="chrome",
        computer_use_uia_enabled=uia,
        computer_use_vlm_enabled=vlm,
        phase3_mode_preset_llm=True,
        thinking_mode="default",
    )


@patch("iris.automation.tools.uia_reader.snapshot_window_uia", return_value=([], "", ""))
@patch("iris.automation.tools.read_screen_summary_text", return_value=(True, "ok", "OCR hello"))
@patch("iris.automation.tools.window_controller.get_active_window_title", return_value="Notepad")
def test_build_perception_ocr_when_uia_empty(
    _active: MagicMock,
    _ocr: MagicMock,
    _uia: MagicMock,
) -> None:
    ctx = AutomationToolContext(settings=_settings(uia=True))
    obs = build_perception_observation(ctx)
    assert obs.perception_source == "ocr"
    assert "OCR hello" in obs.summary


@patch("iris.automation.tools.build_perception_observation")
def test_perceive_desktop_tool_message(mock_build: MagicMock) -> None:
    from iris.automation.perception_types import PerceptionObservation

    mock_build.return_value = PerceptionObservation(
        active_window="Calc",
        summary='{"window":"Calc"}',
        perception_source="uia",
    )
    tool = PerceiveDesktopTool()
    ctx = AutomationToolContext(settings=_settings())
    res = tool.execute(ctx)
    assert res.success
    assert res.message.startswith("perceive:")
