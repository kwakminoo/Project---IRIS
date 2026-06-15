"""Theia ↔ Iris IDE Context Bridge 클라이언트."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# 기본 차단 패턴
_SECRET_PATTERNS = (
  re.compile(r"\.env($|\.)", re.I),
  re.compile(r"id_rsa", re.I),
  re.compile(r"\.pem$", re.I),
  re.compile(r"credentials", re.I),
)
_BINARY_EXTENSIONS = frozenset({
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
  ".zip", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2",
  ".mp3", ".mp4", ".avi", ".bin", ".pyc", ".pyo",
})


@dataclass
class IdeContext:
  workspace_path: str = ""
  active_file_uri: str = ""
  active_file_language: str = ""
  selected_text: str = ""
  selection_range: dict[str, Any] = field(default_factory=dict)
  dirty_state: bool = False

  def summary_line(self) -> str:
    parts: list[str] = []
    if self.workspace_path:
      parts.append(f"Workspace: {Path(self.workspace_path).name}")
    if self.active_file_uri:
      name = Path(self.active_file_uri.replace("file:///", "").replace("file://", "")).name
      parts.append(f"파일: {name}")
    if self.selected_text.strip():
      lines = self.selected_text.strip().splitlines()
      preview = lines[0][:40] + ("…" if len(lines[0]) > 40 else "")
      parts.append(f"선택: {preview}")
    return " · ".join(parts) if parts else "Workspace: —"


def is_context_attachment_allowed(uri: str, selected_text: str = "") -> bool:
  """Secret·binary 파일 context 첨부 차단."""
  path = uri.replace("file:///", "").replace("file://", "")
  lower = path.lower()
  for pat in _SECRET_PATTERNS:
    if pat.search(lower):
      return False
  ext = Path(lower).suffix
  if ext in _BINARY_EXTENSIONS:
    return False
  return True


class IdeBridgeClient:
  """localhost HTTP로 Theia extension과 context 교환."""

  def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
    self._host = host
    self._port = port
    self._context = IdeContext()
    self._lock = threading.Lock()
    self._server: HTTPServer | None = None
    self._thread: threading.Thread | None = None
    self._pending_commands: list[dict[str, Any]] = []

  @property
  def port(self) -> int:
    if self._server is None:
      return self._port
    return int(self._server.server_address[1])

  @property
  def base_url(self) -> str:
    return f"http://{self._host}:{self.port}"

  def start(self) -> None:
    if self._server is not None:
      return
    client = self

    class Handler(BaseHTTPRequestHandler):
      def log_message(self, format: str, *args: object) -> None:
        return

      def do_POST(self) -> None:
        if urlparse(self.path).path != "/context":
          self.send_error(404)
          return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
          data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
          self.send_error(400)
          return
        client._apply_context(data)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

      def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/context":
          snap = client.get_context()
          payload = {
            "workspace_path": snap.workspace_path,
            "active_file_uri": snap.active_file_uri,
            "active_file_language": snap.active_file_language,
            "selected_text": snap.selected_text,
            "selection_range": snap.selection_range,
            "dirty_state": snap.dirty_state,
          }
          self._json_response(payload)
          return
        if path == "/commands":
          cmds = client.pop_commands()
          self._json_response({"commands": cmds})
          return
        self.send_error(404)

      def _json_response(self, obj: object) -> None:
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    self._server = HTTPServer((self._host, self._port), Handler)
    self._port = self.port
    self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
    self._thread.start()

  def stop(self) -> None:
    if self._server is None:
      return
    self._server.shutdown()
    self._server.server_close()
    self._server = None
    self._thread = None

  def _apply_context(self, data: dict[str, Any]) -> None:
    uri = str(data.get("active_file_uri", ""))
    if uri and not is_context_attachment_allowed(uri, str(data.get("selected_text", ""))):
      return
    with self._lock:
      self._context = IdeContext(
        workspace_path=str(data.get("workspace_path", "")),
        active_file_uri=uri,
        active_file_language=str(data.get("active_file_language", "")),
        selected_text=str(data.get("selected_text", "")),
        selection_range=dict(data.get("selection_range") or {}),
        dirty_state=bool(data.get("dirty_state", False)),
      )

  def get_context(self) -> IdeContext:
    with self._lock:
      return IdeContext(
        workspace_path=self._context.workspace_path,
        active_file_uri=self._context.active_file_uri,
        active_file_language=self._context.active_file_language,
        selected_text=self._context.selected_text,
        selection_range=dict(self._context.selection_range),
        dirty_state=self._context.dirty_state,
      )

  def queue_command(self, cmd: dict[str, Any]) -> None:
    with self._lock:
      self._pending_commands.append(cmd)

  def pop_commands(self) -> list[dict[str, Any]]:
    with self._lock:
      cmds = list(self._pending_commands)
      self._pending_commands.clear()
      return cmds

  def build_message_context_block(self) -> str:
    """사용자 메시지에 첨부할 context 블록 (선택·활성 파일만)."""
    ctx = self.get_context()
    if not ctx.active_file_uri and not ctx.selected_text.strip():
      return ""
    lines = ["[IDE Context]"]
    if ctx.active_file_uri:
      lines.append(f"active_file: {ctx.active_file_uri}")
    if ctx.active_file_language:
      lines.append(f"language: {ctx.active_file_language}")
    if ctx.selected_text.strip():
      lines.append("selected_text:")
      lines.append(ctx.selected_text)
    return "\n".join(lines)
