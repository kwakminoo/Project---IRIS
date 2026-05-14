"""주요 앱 실행 파일 경로 자동 탐지 (개인 경로 하드코딩 금지)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List

# 선택: Windows 레지스트리
try:
    import winreg  # type: ignore
except ImportError:
    winreg = None  # type: ignore


def _reg_exe(subkey: str, value_name: str = "") -> str | None:
    """레지스트리에서 UninstallString / (기본) 실행 경로 추정."""
    if winreg is None:
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey)
        try:
            val, _ = winreg.QueryValueEx(key, value_name or None)  # type: ignore[arg-type]
            if isinstance(val, str) and val.lower().endswith(".exe"):
                return val.strip('"')
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)
    except OSError:
        pass
    return None


def _which(name: str) -> str | None:
    return shutil.which(name)


def _path_if_file(p: Path) -> str | None:
    return str(p) if p.is_file() else None


def detect_app_paths() -> Dict[str, str]:
    """
    논리 키 -> 실행 파일 경로.
    실패한 항목은 딕셔너리에 포함하지 않음.
    """
    out: Dict[str, str] = {}

    # PATH
    for key, names in (
        ("python", ["python"]),
        ("code", ["code", "cursor"]),  # VS Code / Cursor CLI
    ):
        for n in names:
            w = _which(n)
            if w:
                out[key] = w
                break

    # 일반적인 설치 위치 (환경 변수 기반)
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")

    candidates: List[tuple[str, Path]] = [
        ("chrome", Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        ("edge", Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        ("discord", Path(local) / "Discord" / "Update.exe"),
        ("steam", Path(pfx86) / "Steam" / "steam.exe"),
        ("league", Path(pfx86) / "Riot Games" / "Riot Client" / "RiotClientServices.exe"),
        ("obs", Path(pf) / "obs-studio" / "bin" / "64bit" / "obs64.exe"),
    ]
    for key, path in candidates:
        exe = _path_if_file(path)
        if exe:
            out[key] = exe

    # 레지스트리 보조
    reg_chrome = _reg_exe(r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
    if reg_chrome and "chrome" not in out:
        out["chrome"] = reg_chrome

    return out
