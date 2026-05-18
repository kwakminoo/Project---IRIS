"""Microsoft Edge 온라인 TTS (edge-tts) 합성."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings


def _sentences_for_ssml(plain: str) -> list[str]:
    """짧은 break용으로 문장 단위 분리."""
    t = plain.strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?。])\s+|\n+", t)
    return [p.strip() for p in parts if p.strip()]


def format_edge_plain_text(plain: str) -> str:
    """edge-tts에는 SSML이 아니라 순수 텍스트만 전달한다."""
    segs = _sentences_for_ssml(plain)
    if not segs:
        segs = [plain.strip() or "네."]
    return "\n".join(segs)


class EdgeTTSEngine:
    """edge-tts로 오디오 파일 생성 (재생은 UI 브리지에서 처리)."""

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings

    async def render_to_file(self, text: str, out_path: Path) -> bool:
        """
        일반 텍스트를 MP3로 저장.

        Returns:
            성공 여부
        """
        try:
            import edge_tts
        except Exception:
            return False

        voice = self._settings.tts_voice
        rate = self._settings.tts_rate
        pitch = self._settings.tts_pitch
        volume = self._settings.tts_volume

        payload = format_edge_plain_text(text)

        try:
            comm = edge_tts.Communicate(payload, voice=voice, rate=rate, pitch=pitch, volume=volume)
            await comm.save(str(out_path))
        except Exception:
            return False
        return out_path.is_file() and out_path.stat().st_size > 0

    def render_to_file_sync(self, text: str, out_path: Path) -> bool:
        """워커 스레드 등에서 동기 호출."""
        try:
            return asyncio.run(self.render_to_file(text, out_path))
        except Exception:
            return False
