"""Chrome 확장 설치 안내 — 브라우저·클립보드."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from iris.monitoring.extension_status import resolve_chrome_extension_dir


@dataclass(frozen=True)
class ExtensionSetupResult:
    ok: bool
    message: str
    extension_dir: Path
    opened_extensions_page: bool


def _find_chrome_exe() -> Path | None:
    import os

    local = os.environ.get("LOCALAPPDATA", "")
    candidates: list[Path] = []
    if local:
        candidates.append(
            Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe"
        )
    candidates.extend(
        (
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        )
    )
    for p in candidates:
        if p.is_file():
            return p
    which = shutil.which("chrome") or shutil.which("google-chrome")
    return Path(which) if which else None


def launch_chrome_extension_setup() -> ExtensionSetupResult:
    """
    확장 폴더 경로 복사 + chrome://extensions 열기.
    실제 「압축해제 로드」는 사용자가 Chrome에서 수행.
    """
    ext_dir = resolve_chrome_extension_dir()
    if not ext_dir.is_dir():
        return ExtensionSetupResult(
            ok=False,
            message=f"확장 폴더를 찾을 수 없습니다:\n{ext_dir}",
            extension_dir=ext_dir,
            opened_extensions_page=False,
        )

    opened = False
    chrome = _find_chrome_exe()
    if chrome:
        try:
            subprocess.Popen(
                [str(chrome), "chrome://extensions/"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            opened = True
        except OSError:
            opened = False

    msg_lines = [
        "1. Chrome 확장 관리(chrome://extensions)에서 개발자 모드를 켭니다.",
        "2. 「압축해제된 확장 프로그램을 로드합니다」→ 아래 폴더를 선택합니다.",
        f"   {ext_dir}",
        "3. Iris Tab Monitor 팝업 → YouTube 등 사이트 체크 → 포트 17777 → 설정 저장.",
    ]
    if not opened:
        msg_lines.insert(0, "Chrome을 수동으로 열고 chrome://extensions 로 이동하세요.")

    return ExtensionSetupResult(
        ok=True,
        message="\n".join(msg_lines),
        extension_dir=ext_dir,
        opened_extensions_page=opened,
    )
