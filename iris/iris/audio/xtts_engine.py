"""Coqui XTTS-v2 로컬 TTS (선택 의존성, lazy loading).

상업 배포 전 Coqui TTS / XTTS-v2 라이선스(CPML 등) 검토가 필요합니다.
참조 음성은 본인 또는 명시적 사용 허가를 받은 음성만 사용하세요.
유명인·타인 목소리 무단 복제 기능은 제공하지 않습니다.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from iris.config.settings import Settings

logger = logging.getLogger(__name__)

# Coqui TTS 선택 import — 미설치 시 Iris는 폴백 TTS로 동작
_XTTS_IMPORT_ERROR: str | None = None
try:
    from TTS.api import TTS as CoquiTTS  # type: ignore[import-untyped]

    _COQUI_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    CoquiTTS = None  # type: ignore[misc, assignment]
    _COQUI_AVAILABLE = False
    _XTTS_IMPORT_ERROR = str(exc)

# CPU에서 긴 문장은 청크로 나눠 합성
_MAX_CHARS_PER_CHUNK_CPU = 120
_MAX_CHARS_PER_CHUNK_GPU = 280


def is_xtts_installed() -> bool:
    return _COQUI_AVAILABLE


def xtts_import_error() -> str | None:
    return _XTTS_IMPORT_ERROR


def resolve_reference_wav(settings: Settings, app_root: Path) -> Path | None:
    """참조 wav 절대 경로. 없으면 None."""
    raw = settings.xtts_reference_wav.strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = app_root / p
    p = p.resolve()
    if p.is_file() and p.stat().st_size > 0:
        return p
    return None


def _split_for_synthesis(text: str, max_chars: int) -> list[str]:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]
    chunks: list[str] = []
    sents = re.split(r"(?<=[.!?。])\s+", t)
    buf = ""
    for s in sents:
        if len(s) > max_chars:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            for i in range(0, len(s), max_chars):
                chunks.append(s[i : i + max_chars].strip())
            continue
        candidate = f"{buf} {s}".strip() if buf else s
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                chunks.append(buf.strip())
            buf = s
    if buf:
        chunks.append(buf.strip())
    return [c for c in chunks if c]


def _cache_key(text: str, preset: str, language: str, speed: float) -> str:
    payload = f"{text}|{preset}|{language}|{speed:.3f}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class XTTSEngine:
    """XTTS-v2 lazy load + 캐시 + 참조 음성 클로닝."""

    def __init__(self, settings: Settings, app_root: Path) -> None:
        self._settings = settings
        self._app_root = app_root
        self._model: Any = None
        self._device = "cpu"
        self._load_lock = threading.Lock()
        self._loading = False
        self._load_error: str | None = None
        self._sample_rate = 24000

    @property
    def is_loading(self) -> bool:
        return self._loading

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def reference_wav_path(self) -> Path | None:
        return resolve_reference_wav(self._settings, self._app_root)

    def _resolve_device(self) -> str:
        want = self._settings.xtts_device
        if want in {"cpu", "cuda"}:
            return want
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def ensure_loaded(self, on_progress: Optional[Callable[[], None]] = None) -> bool:
        """첫 합성 시 모델 로드. UI 스레드에서 호출하지 말 것."""
        if self._model is not None:
            return True
        if not _COQUI_AVAILABLE:
            self._load_error = _XTTS_IMPORT_ERROR or "Coqui TTS 미설치"
            return False
        with self._load_lock:
            if self._model is not None:
                return True
            self._loading = True
            if on_progress:
                on_progress()
            try:
                self._device = self._resolve_device()
                self._model = CoquiTTS(self._settings.xtts_model_name).to(self._device)
                self._load_error = None
                return True
            except Exception as exc:
                self._load_error = str(exc)
                logger.warning("XTTS 모델 로드 실패: %s", exc)
                return False
            finally:
                self._loading = False

    def synthesize_to_wav(
        self,
        text: str,
        out_path: Path,
        *,
        voice_preset: str,
        speed: float,
        apply_fx: Optional[Callable[[Any], Any]] = None,
    ) -> bool:
        """
        text를 out_path(wav)로 합성.

        apply_fx: numpy float32 mono → processed (voice_fx 연동)
        """
        ref = self.reference_wav_path()
        if ref is None:
            return False
        if not self.ensure_loaded():
            return False
        assert self._model is not None

        cache_path: Path | None = None
        if self._settings.xtts_enable_cache:
            cache_dir = Path(self._settings.xtts_cache_dir)
            if not cache_dir.is_absolute():
                cache_dir = self._app_root / cache_dir
            cache_dir.mkdir(parents=True, exist_ok=True)
            key = _cache_key(text, voice_preset, self._settings.xtts_language, speed)
            cache_path = cache_dir / f"{key}.wav"
            if cache_path.is_file() and cache_path.stat().st_size > 0:
                import shutil

                shutil.copy2(cache_path, out_path)
                return True

        max_chunk = (
            _MAX_CHARS_PER_CHUNK_GPU if self._device == "cuda" else _MAX_CHARS_PER_CHUNK_CPU
        )
        chunks = _split_for_synthesis(text.replace("\n", " "), max_chunk)
        if not chunks:
            return False

        try:
            import numpy as np
            import soundfile as sf
        except Exception as exc:
            self._load_error = f"soundfile/numpy 필요: {exc}"
            return False

        segments: list[np.ndarray] = []
        lang = self._settings.xtts_language
        for chunk in chunks:
            wav_path = out_path.with_suffix(".part.wav")
            self._model.tts_to_file(
                text=chunk,
                file_path=str(wav_path),
                speaker_wav=str(ref),
                language=lang,
                speed=speed,
            )
            data, sr = sf.read(str(wav_path), dtype="float32")
            self._sample_rate = int(sr)
            if data.ndim > 1:
                data = data.mean(axis=1)
            segments.append(data.astype(np.float32))
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass

        if not segments:
            return False

        merged = np.concatenate(segments)
        if apply_fx is not None:
            merged = apply_fx(merged)
        sf.write(str(out_path), merged, self._sample_rate)
        if cache_path is not None:
            try:
                import shutil

                shutil.copy2(out_path, cache_path)
            except OSError:
                pass
        return out_path.is_file() and out_path.stat().st_size > 0
