"""IDE 의존성 복구 — 사용자 명시 클릭 후 Iris venv에 WebEngine 설치."""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows에서 검증된 PyQt6 + WebEngine 조합
_PINNED_PYQT6 = "PyQt6==6.11.0"
_PINNED_WEBENGINE = "PyQt6-WebEngine==6.11.0"


@dataclass
class IdeRecoveryResult:
    success: bool
    message: str
    log_path: str


def _recovery_log_path() -> Path:
    d = Path.home() / ".iris" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ide-recovery.log"


def recover_webengine(*, install_theia: bool = False) -> IdeRecoveryResult:
    """Iris 실행 Python으로 WebEngine 재설치."""
    log_path = _recovery_log_path()
    lines: list[str] = [f"python={sys.executable}", f"install_theia={install_theia}"]

    def _run(cmd: list[str]) -> tuple[int, str]:
        lines.append(f"$ {' '.join(cmd)}")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                shell=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            lines.append(out[-4000:])
            return proc.returncode, out
        except Exception as exc:
            lines.append(f"ERROR: {exc}")
            return 1, str(exc)

    code, _ = _run([sys.executable, "-m", "pip", "install", _PINNED_PYQT6, _PINNED_WEBENGINE])
    if code != 0:
        log_path.write_text("\n".join(lines), encoding="utf-8")
        return IdeRecoveryResult(False, "PyQt6-WebEngine 설치 실패 — 로그를 확인하세요.", str(log_path))

    verify = subprocess.run(
        [sys.executable, "-c", "from PyQt6.QtWebEngineWidgets import QWebEngineView"],
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )
    if verify.returncode != 0:
        lines.append(verify.stderr or verify.stdout or "verify failed")
        log_path.write_text("\n".join(lines), encoding="utf-8")
        return IdeRecoveryResult(False, "설치 후 WebEngine import 검증 실패", str(log_path))

    if install_theia:
        from iris.infrastructure.ide.ide_workspace_resolver import _find_repo_root

        root = _find_repo_root()
        setup = root / "scripts" / "setup-iris-ide.ps1"
        build = root / "scripts" / "build-iris-ide.ps1"
        for script in (setup, build):
            if script.is_file():
                code, _ = _run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(script),
                    ]
                )
                if code != 0:
                    log_path.write_text("\n".join(lines), encoding="utf-8")
                    return IdeRecoveryResult(
                        False,
                        f"Theia 스크립트 실패: {script.name}",
                        str(log_path),
                    )

    lines.append("OK")
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return IdeRecoveryResult(True, "IDE 환경 복구 완료. IDE를 다시 시도하세요.", str(log_path))
