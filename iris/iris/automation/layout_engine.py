"""모니터 기반 레이아웃 좌표 계산."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from iris.config.preset_modes import LayoutHint


@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int


def monitors_geometry() -> List[Tuple[int, int, int, int]]:
    """(x, y, w, h) 리스트."""
    try:
        from screeninfo import get_monitors

        return [(m.x, m.y, m.width, m.height) for m in get_monitors()]
    except Exception:
        return [(0, 0, 1920, 1080)]


def rect_for_hint(hint: LayoutHint) -> Rect:
    """단일 힌트를 픽셀 직사각형으로."""
    mons = monitors_geometry()
    idx = max(0, min(hint.monitor_index, len(mons) - 1))
    mx, my, mw, mh = mons[idx]
    left = mx + int(mw * hint.left)
    top = my + int(mh * hint.top)
    width = max(200, int(mw * hint.width))
    height = max(200, int(mh * hint.height))
    return Rect(left=left, top=top, width=width, height=height)
