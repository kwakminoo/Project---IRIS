"""QWebEnginePage — Chromium 콘솔·렌더 프로세스·내비게이션 오류 수집."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage

logger = logging.getLogger(__name__)

_LOG_PATH = Path.home() / ".iris" / "logs" / "ide-webengine.log"


def ide_webengine_log_path() -> Path:
    return _LOG_PATH


def _enum_label(value: object) -> str:
    """PyQt6 enum — int() 변환 실패 방지 (Python 3.13 + Qt6)."""
    try:
        name = getattr(value, "name", None)
        if name:
            return str(name)
        raw = getattr(value, "value", None)
        if raw is not None:
            return str(raw)
    except Exception:
        pass
    return str(value)


def _append_log(line: str, *, level: str = "INFO") -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prefix = "!!" if level in {"ERROR", "WARNING"} else ""
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(f"[{ts}] {prefix}{line}\n")
    except OSError as exc:
        logger.warning("ide-webengine.log write failed: %s", exc)


def tail_webengine_log(*, max_lines: int = 200) -> str:
    if not _LOG_PATH.is_file():
        return "(ide-webengine.log 없음)"
    try:
        lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except OSError as exc:
        return f"(로그 읽기 실패: {exc})"


class IrisWebEnginePage(QWebEnginePage):
    """Theia 임베드용 디버그 페이지."""

    def __init__(
        self,
        parent=None,
        *,
        ide_port_callback: Callable[[], int | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_url = ""
        self._ide_port_callback = ide_port_callback

    def current_logged_url(self) -> str:
        return self._current_url

    def _allowed_port(self) -> int | None:
        if self._ide_port_callback is not None:
            return self._ide_port_callback()
        if self._current_url:
            parsed = urlparse(self._current_url)
            return parsed.port
        return None

    def _is_navigation_allowed(self, url: QUrl) -> bool:
        scheme = url.scheme().lower()
        if scheme in ("about",):
            return url.toString() in ("about:blank", "about:srcdoc")
        if scheme in ("http", "https", "ws", "wss"):
            host = url.host().lower()
            if host == "localhost":
                host = "127.0.0.1"
            if host != "127.0.0.1":
                _append_log(f"Navigation BLOCKED external host: {url.toString()}", level="WARNING")
                return False
            port = url.port()
            if port <= 0:
                port = 443 if scheme in ("https", "wss") else 80
            allowed = self._allowed_port()
            if allowed is not None and port != allowed:
                _append_log(
                    f"Navigation BLOCKED wrong port {port} (expected {allowed}): {url.toString()}",
                    level="WARNING",
                )
                return False
            return True
        if scheme == "file":
            _append_log(f"Navigation BLOCKED file:// {url.toString()}", level="WARNING")
            return False
        _append_log(f"Navigation BLOCKED scheme={scheme} {url.toString()}", level="WARNING")
        return False

    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        try:
            lvl = _enum_label(level)
            line = f"JS[{lvl}] url={self._current_url} {source_id}:{line_number} {message}"
            log_level = "INFO"
            if lvl.upper() in {"ERROR", "WARNING"}:
                log_level = lvl.upper()
                if any(
                    kw in message.lower()
                    for kw in (
                        "websocket",
                        "content security policy",
                        "csp",
                        "invalid host",
                        "origin",
                        "failed to fetch",
                        "mixed content",
                        "service worker",
                    )
                ):
                    line = f"JS[{lvl}] **NETWORK** url={self._current_url} {source_id}:{line_number} {message}"
            _append_log(line, level=log_level)
            if log_level != "INFO":
                logger.warning("WebEngine %s", line)
            else:
                logger.debug("WebEngine JS[%s] %s:%s %s", lvl, source_id, line_number, message)
        except Exception as exc:
            logger.warning("javaScriptConsoleMessage handler failed: %s", exc)

    def renderProcessTerminated(
        self,
        termination_status: QWebEnginePage.RenderProcessTerminationStatus,
        exit_code: int,
    ) -> None:
        try:
            status = _enum_label(termination_status)
            msg = f"RenderProcessTerminated status={status} exit={exit_code} url={self._current_url}"
            _append_log(msg, level="ERROR")
            logger.error(msg)
        except Exception as exc:
            logger.warning("renderProcessTerminated handler failed: %s", exc)

    def certificateError(self, error) -> bool:  # noqa: ANN001
        try:
            _append_log(
                f"CertificateError: {error.errorDescription()} url={error.url().toString()}",
                level="WARNING",
            )
        except Exception as exc:
            logger.warning("certificateError handler failed: %s", exc)
        return False

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # noqa: ANN001
        try:
            allowed = self._is_navigation_allowed(url)
            if is_main_frame:
                if allowed:
                    self._current_url = url.toString()
                _append_log(
                    f"Navigation{'(main)' if is_main_frame else ''} "
                    f"{'ALLOW' if allowed else 'DENY'}: {url.toString()}"
                )
            if not allowed:
                return False
        except Exception as exc:
            logger.warning("acceptNavigationRequest failed: %s", exc)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)
