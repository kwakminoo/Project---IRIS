"""Chrome 확장 → 로컬 HTTP 수신."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from typing import Callable


def start_extension_server(
    host: str,
    port: int,
    token: str,
    on_payload: Callable[[dict], None],
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """백그라운드 스레드에서 서버 시작."""

    class ExtensionHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args_) -> None:  # noqa: A003
            return

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization",
            )

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/ingest", "/ingest/"):
                self.send_error(404)
                return
            auth = self.headers.get("Authorization") or ""
            if token:
                expected = f"Bearer {token}".strip()
                if auth.strip() != expected:
                    self.send_error(401)
                    return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            try:
                on_payload(data)
            except Exception:
                pass
            self.send_response(204)
            self._cors()
            self.end_headers()

    server = ThreadingHTTPServer((host, port), ExtensionHandler)  # noqa: S104
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    return server, th
