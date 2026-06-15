"""QWebEnginePage — Chromium 콘솔·렌더 프로세스·내비게이션 오류 수집."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

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


def _append_log(line: str) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(f"[{ts}] {line}\n")
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_url = ""

    def current_logged_url(self) -> str:
        return self._current_url

    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        # Qt 콜백 예외는 프로세스 종료로 이어질 수 있음 — 절대 밖으로 던지지 않음
        try:
            lvl = _enum_label(level)
            _append_log(f"JS[{lvl}] {source_id}:{line_number} {message}")
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
            _append_log(msg)
            logger.error(msg)
        except Exception as exc:
            logger.warning("renderProcessTerminated handler failed: %s", exc)

    def certificateError(self, error) -> bool:  # noqa: ANN001
        try:
            _append_log(f"CertificateError: {error.errorDescription()} url={error.url().toString()}")
        except Exception as exc:
            logger.warning("certificateError handler failed: %s", exc)
        return False

    def acceptNavigationRequest(self, url: QUrl, _type, is_main_frame: bool) -> bool:
        try:
            if is_main_frame:
                self._current_url = url.toString()
                _append_log(f"Navigation: {self._current_url}")
        except Exception as exc:
            logger.warning("acceptNavigationRequest log failed: %s", exc)
        return super().acceptNavigationRequest(url, _type, is_main_frame)
