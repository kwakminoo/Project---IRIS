"""화면 캡처 (기본은 메모리만, 디스크 저장은 설정으로)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from iris.config.settings import Settings


@dataclass
class CaptureResult:
    """RGBA 또는 RGB bytes + 크기."""

    width: int
    height: int
    rgb_bytes: bytes


def capture_full_screen(_settings: Settings) -> Optional[CaptureResult]:
    """전체 화면 캡처. 실패 시 None."""
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            w, h = shot.width, shot.height
            # BGRA → RGB
            raw = shot.bgra
            rgb = bytearray(w * h * 3)
            for i in range(w * h):
                b, g, r = raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2]
                rgb[i * 3] = r
                rgb[i * 3 + 1] = g
                rgb[i * 3 + 2] = b
            return CaptureResult(w, h, bytes(rgb))
    except Exception:
        return None


def capture_region(left: int, top: int, width: int, height: int) -> Optional[CaptureResult]:
    """지정 영역."""
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            w, h = shot.width, shot.height
            raw = shot.bgra
            rgb = bytearray(w * h * 3)
            for i in range(w * h):
                b, g, r = raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2]
                rgb[i * 3] = r
                rgb[i * 3 + 1] = g
                rgb[i * 3 + 2] = b
            return CaptureResult(w, h, bytes(rgb))
    except Exception:
        return None


def maybe_save_debug_screenshot(settings: Settings, cap: CaptureResult, path: Path) -> None:
    """store_screenshots=True일 때만 디스크 저장."""
    if not settings.store_screenshots:
        return
    try:
        from PIL import Image  # type: ignore

        img = Image.frombytes("RGB", (cap.width, cap.height), cap.rgb_bytes)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
    except Exception:
        pass
