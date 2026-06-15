"""Theia Browser Backend 프로세스 관리."""

from __future__ import annotations

import logging
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from iris.infrastructure.ide.ide_workspace_resolver import _find_repo_root

logger = logging.getLogger(__name__)

_START_TIMEOUT_SEC = 45.0
_HOST = "127.0.0.1"
_PORT_MIN = 3100
_PORT_MAX = 3199


@dataclass
class BackendStatus:
    running: bool
    frontend_url: str = ""
    port: int = 0
    error: str = ""
    log_path: str = ""


def _find_frontend_entry() -> Optional[Path]:
    root = _find_repo_root()
    candidates = [
        root / "iris-ide" / "applications" / "browser" / "lib" / "frontend" / "index.html",
        root / "iris-ide" / "lib" / "frontend" / "index.html",
        root / "iris" / "iris" / "resources" / "ide" / "lib" / "frontend" / "index.html",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _find_node() -> Optional[str]:
    import shutil

    root = _find_repo_root()
    bundled = [
        root / "iris-ide" / "node_modules" / "node-win-x64" / "bin" / "node.exe",
        root / "iris-ide" / "node_modules" / "node" / "bin" / "node.exe",
    ]
    for candidate in bundled:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("node")


def tail_backend_log(*, max_lines: int = 200) -> str:
    path = Path.home() / ".iris" / "logs" / "ide-backend.log"
    if not path.is_file():
        return "(ide-backend.log 없음)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except OSError as exc:
        return f"(로그 읽기 실패: {exc})"


class IdeBackendManager:
    """Theia backend child process — MainWindow에서 직접 Popen 금지."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._port: int = 0
        self._workspace: Path | None = None
        self._log_file: Optional[Path] = None
        self._log_fp = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def frontend_url(self) -> str:
        if self._port:
            return f"http://{_HOST}:{self._port}"
        return ""

    def _log_dir(self) -> Path:
        d = Path.home() / ".iris" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _find_backend_entry(self) -> Optional[Path]:
        root = _find_repo_root()
        candidates = [
            root / "iris-ide" / "applications" / "browser" / "lib" / "backend" / "main.js",
            root / "iris-ide" / "lib" / "backend" / "main.js",
            root / "iris" / "iris" / "resources" / "ide" / "lib" / "backend" / "main.js",
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def _backend_cwd(self, entry: Path) -> Path:
        # applications/browser/lib/backend/main.js → applications/browser
        return entry.parent.parent.parent

    def _pick_port(self) -> int:
        for port in range(_PORT_MIN, _PORT_MAX + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((_HOST, port))
                except OSError:
                    continue
                return port
        raise RuntimeError("사용 가능한 localhost 포트를 찾지 못했습니다.")

    def _fetch(self, url: str, *, timeout: float = 2.0) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                body = resp.read(65536).decode("utf-8", errors="replace")
                return int(resp.status), body
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read(65536).decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return int(exc.code), body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, str(exc)

    def _health_ok(self, port: int) -> bool:
        """HTTP 200 + Theia HTML + bundle 경로 응답."""
        base = f"http://{_HOST}:{port}"
        status, body = self._fetch(f"{base}/")
        if status < 200 or status >= 500:
            return False
        if "theia" not in body.lower() and "preload" not in body.lower():
            return False
        bundle_status, _ = self._fetch(f"{base}/bundle.js")
        if bundle_status and bundle_status >= 500:
            return False
        return True

    def ensure_running(self, workspace: Path) -> BackendStatus:
        if self.is_running and self._workspace == workspace.resolve():
            if self._health_ok(self._port):
                return BackendStatus(
                    True,
                    self.frontend_url,
                    self._port,
                    log_path=str(self._log_path or ""),
                )
        if self.is_running:
            self.shutdown()

        entry = self._find_backend_entry()
        if entry is None:
            return BackendStatus(
                False,
                error="Theia Build 없음 — scripts\\build-iris-ide.ps1 실행 필요",
            )
        frontend = _find_frontend_entry()
        if frontend is None:
            return BackendStatus(
                False,
                error="Theia frontend 산출물 없음 — scripts\\build-iris-ide.ps1 실행 필요",
            )

        node = _find_node()
        if node is None:
            return BackendStatus(False, error="Node 없음 — Node 18+ 및 scripts\\setup-iris-ide.ps1 필요")

        port = self._pick_port()
        log_path = self._log_dir() / "ide-backend.log"
        self._log_file = log_path
        self._close_log_fp()
        self._log_fp = open(log_path, "a", encoding="utf-8")
        self._log_fp.write(
            f"\n--- backend start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            f"node={node}\nworkspace={workspace.resolve()}\nport={port}\n"
        )
        self._log_fp.flush()

        cmd = [
            node,
            str(entry),
            str(workspace.resolve()),
            f"--hostname={_HOST}",
            f"--port={port}",
        ]
        cwd = self._backend_cwd(entry)
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=self._log_fp,
                stderr=subprocess.STDOUT,
                shell=False,
                cwd=str(cwd),
            )
        except OSError as exc:
            self._close_log_fp()
            return BackendStatus(False, error=f"Backend 시작 실패: {exc}", log_path=str(log_path))

        self._port = port
        self._workspace = workspace.resolve()
        logger.info("Theia backend starting pid=%s port=%s", self._proc.pid, port)

        deadline = time.monotonic() + _START_TIMEOUT_SEC
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                code = self._proc.returncode
                tail = tail_backend_log(max_lines=80)
                return BackendStatus(
                    False,
                    error=f"Backend 조기 종료 (exit {code})\n\n{tail}",
                    log_path=str(log_path),
                )
            if self._health_ok(port):
                return BackendStatus(True, self.frontend_url, port, log_path=str(log_path))
            time.sleep(0.4)

        self.shutdown()
        tail = tail_backend_log(max_lines=80)
        return BackendStatus(
            False,
            error=f"Backend Timeout ({_START_TIMEOUT_SEC:.0f}s)\n\n{tail}",
            log_path=str(log_path),
        )

    @property
    def _log_path(self) -> Optional[Path]:
        return self._log_file

    def _close_log_fp(self) -> None:
        if self._log_fp is not None:
            try:
                self._log_fp.close()
            except OSError:
                pass
            self._log_fp = None

    def shutdown(self) -> None:
        if self._proc is None:
            self._close_log_fp()
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._port = 0
        self._workspace = None
        self._close_log_fp()
