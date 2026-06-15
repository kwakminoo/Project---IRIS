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


class IdeBackendManager:
  """Theia backend child process — MainWindow에서 직접 Popen 금지."""

  def __init__(self) -> None:
    self._proc: subprocess.Popen[str] | None = None
    self._port: int = 0
    self._workspace: Path | None = None
    self._log_file: Optional[Path] = None

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

  def _health_ok(self, port: int) -> bool:
    url = f"http://{_HOST}:{port}/"
    try:
      with urllib.request.urlopen(url, timeout=2) as resp:
        return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
      return False

  def ensure_running(self, workspace: Path) -> BackendStatus:
    if self.is_running and self._workspace == workspace.resolve():
      if self._health_ok(self._port):
        return BackendStatus(True, self.frontend_url, self._port, log_path=str(self._log_path or ""))
    if self.is_running:
      self.shutdown()
    entry = self._find_backend_entry()
    if entry is None:
      return BackendStatus(
        False,
        error="Iris IDE가 아직 준비되지 않았습니다.\n\n설정: scripts\\setup-iris-ide.ps1\n빌드: scripts\\build-iris-ide.ps1",
      )
    node = _find_node()
    if node is None:
      return BackendStatus(False, error="Node.js를 찾을 수 없습니다. Node 18+를 설치하세요.")
    port = self._pick_port()
    log_path = self._log_dir() / "ide-backend.log"
    self._log_file = log_path
    log_fp = open(log_path, "a", encoding="utf-8")
    cmd = [
      node,
      str(entry),
      str(workspace.resolve()),
      f"--hostname={_HOST}",
      f"--port={port}",
    ]
    try:
      self._proc = subprocess.Popen(
        cmd,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        shell=False,
        cwd=str(entry.parent.parent.parent),
      )
    except OSError as exc:
      log_fp.close()
      return BackendStatus(False, error=str(exc), log_path=str(log_path))
    self._port = port
    self._workspace = workspace.resolve()
    deadline = time.monotonic() + _START_TIMEOUT_SEC
    while time.monotonic() < deadline:
      if self._proc.poll() is not None:
        return BackendStatus(
          False,
          error="Theia backend가 조기 종료되었습니다.",
          log_path=str(log_path),
        )
      if self._health_ok(port):
        return BackendStatus(True, self.frontend_url, port, log_path=str(log_path))
      time.sleep(0.4)
    return BackendStatus(
      False,
      error="Theia backend health check 시간 초과",
      log_path=str(log_path),
    )

  @property
  def _log_path(self) -> Optional[Path]:
    return self._log_file

  def shutdown(self) -> None:
    if self._proc is None:
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


def _find_node() -> Optional[str]:
  import shutil

  return shutil.which("node")
