"""프로세스 실행."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional


def launch_executable(exe_path: str, cwd: Optional[Path] = None) -> tuple[bool, str]:
    """앱 실행. 실패 시 (False, reason)."""
    try:
        subprocess.Popen(  # noqa: S603
            [exe_path],
            cwd=str(cwd) if cwd else None,
            shell=False,
        )
        return True, "ok"
    except OSError as e:
        return False, str(e)


def launch_by_key(app_paths: Dict[str, str], key: str) -> tuple[bool, str]:
    """논리 키로 실행."""
    path = app_paths.get(key)
    if not path:
        return False, f"경로 없음: {key}"
    return launch_executable(path)
