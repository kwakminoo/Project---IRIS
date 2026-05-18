"""TTS 통합 관리 — XTTS-v2 + Edge/pyttsx3 폴백."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QMetaObject, Qt, pyqtSignal, pyqtSlot

from iris.audio.audio_player import AudioPlayer
from iris.audio.fallback_tts_engine import FallbackTTSEngine
from iris.audio.voice_fx import apply_voice_fx
from iris.audio.xtts_engine import XTTSEngine, is_xtts_installed, resolve_reference_wav
from iris.config.settings import Settings

logger = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parent.parent.parent
_PRESETS_PATH = _APP_ROOT / "config" / "voice_presets.json"


class TtsStatus(Enum):
    """UI 표시용 TTS 상태."""

    IDLE = auto()
    XTTS_READY = auto()
    LOADING_XTTS = auto()
    USING_FALLBACK = auto()
    REFERENCE_MISSING = auto()
    TTS_ERROR = auto()
    SYNTHESIZING = auto()


def load_voice_presets() -> dict[str, Any]:
    if not _PRESETS_PATH.is_file():
        return {}
    try:
        return json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_voice_preset(settings: Settings, mode: str) -> tuple[str, dict[str, Any]]:
    presets = load_voice_presets()
    name = mode if mode in presets else settings.tts_voice_preset
    if name not in presets:
        name = "iris_default" if "iris_default" in presets else next(iter(presets), "iris_default")
    return name, presets.get(name, {"speed": 1.0, "fx": {"enabled": False}})


class TTSManager(QObject):
    """
    TTS_PROVIDER에 따라 XTTS 또는 폴백을 사용한다.

    - speak: 백그라운드 합성 → 메인 스레드 재생
    - stop / is_speaking: barge-in 연동
    - status_changed: UI 상태 라벨 갱신
    """

    status_changed = pyqtSignal(object)  # TtsStatus

    def __init__(
        self,
        settings: Settings,
        player: AudioPlayer | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._player = player or AudioPlayer(self)
        if self._player.parent() is None:
            self._player.setParent(self)
        self._fallback = FallbackTTSEngine(settings)
        self._xtts = XTTSEngine(settings, _APP_ROOT)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending_on_done: Optional[Callable[[], None]] = None
        self._playback_token = 0
        self._speaking = False
        self._status = TtsStatus.IDLE
        self._last_user_notice: str | None = None

        self._player.playback_finished.connect(self._on_playback_finished)
        self._refresh_initial_status()

    @property
    def playback_gen(self) -> int:
        return self._playback_token

    @property
    def status(self) -> TtsStatus:
        return self._status

    @property
    def status_label(self) -> str:
        labels = {
            TtsStatus.IDLE: "TTS: 대기",
            TtsStatus.XTTS_READY: "TTS: XTTS Ready",
            TtsStatus.LOADING_XTTS: "TTS: Loading XTTS…",
            TtsStatus.USING_FALLBACK: "TTS: Using fallback",
            TtsStatus.REFERENCE_MISSING: "TTS: Reference voice missing",
            TtsStatus.TTS_ERROR: "TTS: Error",
            TtsStatus.SYNTHESIZING: "TTS: 합성 중…",
        }
        base = labels.get(self._status, "TTS")
        if self._last_user_notice:
            return f"{base} — {self._last_user_notice}"
        return base

    def is_speaking(self) -> bool:
        return self._speaking or self._player.is_playing()

    def _set_status(self, status: TtsStatus, notice: str | None = None) -> None:
        self._status = status
        if notice is not None:
            self._last_user_notice = notice
        self.status_changed.emit(status)

    def _refresh_initial_status(self) -> None:
        if self._settings.tts_provider != "xtts":
            self._set_status(TtsStatus.IDLE)
            return
        if not is_xtts_installed():
            self._set_status(TtsStatus.USING_FALLBACK, "XTTS 미설치")
            return
        if resolve_reference_wav(self._settings, _APP_ROOT) is None:
            self._set_status(TtsStatus.REFERENCE_MISSING)
            return
        self._set_status(TtsStatus.XTTS_READY)

    def _on_playback_finished(self) -> None:
        self._speaking = False
        self._invoke_done()
        self._refresh_initial_status()

    def _invoke_done(self) -> None:
        with self._lock:
            cb = self._pending_on_done
            self._pending_on_done = None
        if cb:
            cb()

    @pyqtSlot()
    def _defer_invoke_done(self) -> None:
        self._speaking = False
        self._invoke_done()
        self._refresh_initial_status()

    def stop(self) -> None:
        self._stop.set()
        self._playback_token += 1
        self._speaking = False
        self._fallback.stop()
        self._player.stop()
        self._refresh_initial_status()

    def speak(
        self,
        text: str,
        mode: str = "normal",
        *,
        on_synthesis_start: Optional[Callable[[], None]] = None,
        on_playback_start: Optional[Callable[[], None]] = None,
        on_start: Optional[Callable[[], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        백그라운드 합성·재생. UI 스레드를 블로킹하지 않음.

        on_start: 레거시 — on_playback_start와 동일
        on_synthesis_start: 합성 시작 (PROCESSING)
        on_playback_start: 재생 시작 (RESPONDING)
        """
        playback_start = on_playback_start or on_start
        self.stop()
        self._stop.clear()
        with self._lock:
            self._pending_on_done = on_done
        self._playback_token += 1
        token = self._playback_token

        preset_name, preset = resolve_voice_preset(self._settings, mode)
        preset_speed = float(preset.get("speed", 1.0))
        speed = self._settings.xtts_speed * preset_speed

        def run() -> None:
            if on_synthesis_start:
                on_synthesis_start()
            self._set_status(TtsStatus.SYNTHESIZING)

            want_xtts = self._settings.tts_provider == "xtts"
            notice: str | None = None

            if want_xtts and is_xtts_installed():
                ref = resolve_reference_wav(self._settings, _APP_ROOT)
                if ref is None:
                    notice = "아이리스 기준 음성 파일이 없습니다. fallback 음성으로 재생합니다."
                    self._set_status(TtsStatus.REFERENCE_MISSING, notice)
                else:
                    self._set_status(TtsStatus.LOADING_XTTS)

                    def _on_load_progress() -> None:
                        self._set_status(TtsStatus.LOADING_XTTS)

                    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="iris_xtts_")
                    os.close(fd)
                    out = Path(tmp)

                    fx_block = preset.get("fx") if self._settings.tts_enable_voice_fx else None
                    use_fx = bool(fx_block and fx_block.get("enabled"))

                    def _apply_fx(audio):  # type: ignore[no-untyped-def]
                        return apply_voice_fx(
                            audio,
                            fx_block,
                            sample_rate=self._xtts._sample_rate,
                            global_enabled=self._settings.tts_enable_voice_fx,
                        )

                    ok = self._xtts.synthesize_to_wav(
                        text,
                        out,
                        voice_preset=preset_name,
                        speed=speed,
                        apply_fx=_apply_fx if use_fx else None,
                    )
                    if self._stop.is_set() or token != self.playback_gen:
                        try:
                            out.unlink(missing_ok=True)
                        except OSError:
                            pass
                        QMetaObject.invokeMethod(
                            self,
                            "_defer_invoke_done",
                            Qt.ConnectionType.QueuedConnection,
                        )
                        return
                    if ok and out.is_file() and out.stat().st_size > 0:
                        self._set_status(TtsStatus.XTTS_READY)
                        if playback_start:
                            playback_start()
                        self._speaking = True
                        self._player.play_file.emit(token, str(out))
                        return
                    notice = notice or "XTTS 합성에 실패했습니다. fallback으로 재생합니다."
                    self._set_status(TtsStatus.TTS_ERROR, notice)
            elif want_xtts and not is_xtts_installed():
                notice = "XTTS 패키지가 설치되지 않았습니다. fallback으로 재생합니다."
                self._set_status(TtsStatus.USING_FALLBACK, notice)

            # 폴백 경로
            self._set_status(TtsStatus.USING_FALLBACK, notice)
            bridge_ok = self._player.is_available()
            if self._fallback.provider == "edge" and bridge_ok:
                fd, tmp = tempfile.mkstemp(suffix=".mp3", prefix="iris_edge_")
                os.close(fd)
                out_mp3 = Path(tmp)
                try:
                    ok = self._fallback.render_to_file_sync(text, out_mp3)
                    if self._stop.is_set() or token != self.playback_gen:
                        try:
                            out_mp3.unlink(missing_ok=True)
                        except OSError:
                            pass
                        QMetaObject.invokeMethod(
                            self,
                            "_defer_invoke_done",
                            Qt.ConnectionType.QueuedConnection,
                        )
                        return
                    if ok and out_mp3.is_file() and out_mp3.stat().st_size > 0:
                        if playback_start:
                            playback_start()
                        self._speaking = True
                        self._player.play_file.emit(token, str(out_mp3))
                        return
                except Exception:
                    try:
                        out_mp3.unlink(missing_ok=True)
                    except OSError:
                        pass

            if self._stop.is_set() or token != self.playback_gen:
                QMetaObject.invokeMethod(
                    self,
                    "_defer_invoke_done",
                    Qt.ConnectionType.QueuedConnection,
                )
                return
            if playback_start:
                playback_start()
            self._speaking = True
            self._fallback.speak_blocking(text, on_start=None, on_done=self._invoke_done)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
