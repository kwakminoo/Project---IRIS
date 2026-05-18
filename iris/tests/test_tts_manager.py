"""TTSManager 단위 테스트 (XTTS 미설치 환경 포함)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from iris.audio.tts_manager import TTSManager, TtsStatus, load_voice_presets, resolve_voice_preset
from iris.audio.xtts_engine import _split_for_synthesis, is_xtts_installed, resolve_reference_wav
from iris.config.settings import load_settings


def test_voice_presets_load() -> None:
    presets = load_voice_presets()
    assert "iris_default" in presets
    assert "iris_jarvis" in presets


def test_resolve_voice_preset_fallback() -> None:
    settings = load_settings()
    name, preset = resolve_voice_preset(settings, "unknown_mode")
    assert name in load_voice_presets()
    assert "speed" in preset


def test_split_long_text_for_cpu() -> None:
    long_text = "첫 문장입니다. " * 30
    chunks = _split_for_synthesis(long_text, 80)
    assert len(chunks) >= 2
    assert all(len(c) <= 80 for c in chunks)


def test_reference_wav_missing_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "XTTS_REFERENCE_WAV=assets/voices/does_not_exist.wav\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    settings = load_settings(env)
    app_root = tmp_path
    assert resolve_reference_wav(settings, app_root) is None


def test_tts_manager_initial_status_without_xtts() -> None:
    settings = load_settings()
    mgr = TTSManager(settings)
    if settings.tts_provider == "xtts" and not is_xtts_installed():
        assert mgr.status in (TtsStatus.USING_FALLBACK, TtsStatus.REFERENCE_MISSING)
    else:
        assert mgr.status in (TtsStatus.IDLE, TtsStatus.XTTS_READY, TtsStatus.REFERENCE_MISSING)


def test_tts_manager_stop_clears_speaking() -> None:
    settings = load_settings()
    player = MagicMock()
    player.is_playing.return_value = False
    player.is_available.return_value = True
    mgr = TTSManager(settings, player=player)
    mgr.stop()
    assert not mgr.is_speaking()


@patch("iris.audio.tts_manager.is_xtts_installed", return_value=False)
def test_speak_falls_back_when_xtts_not_installed(_mock_xtts: MagicMock) -> None:
    from dataclasses import replace

    settings = replace(load_settings(), tts_provider="xtts")
    player = MagicMock()
    player.is_available.return_value = True
    player.is_playing.return_value = False

    mgr = TTSManager(settings, player=player)
    with patch.object(mgr._fallback, "render_to_file_sync", return_value=False):
        with patch.object(mgr._fallback, "speak_blocking") as mock_speak:
            mgr.speak("좋아요. 바로 준비할게요.")
            import time

            time.sleep(0.4)
            mock_speak.assert_called()
    mgr.stop()
