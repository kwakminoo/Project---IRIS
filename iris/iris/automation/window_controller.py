"""창 검색·포커스·이동·크기 (Windows)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class WindowInfo:
    title: str
    left: int
    top: int
    width: int
    height: int


def get_active_window_title() -> str:
    """현재 포커스 창 제목 (실패 시 빈 문자열)."""
    try:
        import pygetwindow as gw  # type: ignore

        w = gw.getActiveWindow()
        if w and w.title:
            return str(w.title)
    except Exception:
        pass
    return ""


def list_window_titles() -> List[str]:
    """제목 목록 (가능할 때만)."""
    try:
        import pygetwindow as gw  # type: ignore
    except Exception:
        return []
    try:
        return [w.title for w in gw.getAllWindows() if w.title]
    except Exception:
        return []


def find_windows_by_title_substring(sub: str) -> List[WindowInfo]:
    try:
        import pygetwindow as gw  # type: ignore
    except Exception:
        return []
    out: List[WindowInfo] = []
    sub_l = sub.lower()
    try:
        for w in gw.getAllWindows():
            if not w.title:
                continue
            if sub_l in w.title.lower():
                out.append(
                    WindowInfo(w.title, int(w.left), int(w.top), int(w.width), int(w.height))
                )
    except Exception:
        pass
    return out


def focus_and_place(title_sub: str, left: int, top: int, width: int, height: int) -> tuple[bool, str]:
    """첫 매칭 창에 포커스 및 위치/크기."""
    try:
        import pygetwindow as gw  # type: ignore
    except Exception as e:
        return False, f"pygetwindow 없음: {e}"
    try:
        wins = [w for w in gw.getAllWindows() if w.title and title_sub.lower() in w.title.lower()]
        if not wins:
            return False, "창 없음"
        w = wins[0]
        try:
            w.activate()
        except Exception:
            pass
        w.moveTo(left, top)
        w.resizeTo(width, height)
        return True, "ok"
    except Exception as e:
        return False, str(e)
