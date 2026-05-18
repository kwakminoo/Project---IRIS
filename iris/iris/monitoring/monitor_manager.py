"""모니터링 오케스트레이션: 수집 → 감지 → 알림 → DB."""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from iris.config.settings import Settings
from iris.monitoring import desktop_window_monitor, ocr_engine, screen_capture
from iris.monitoring.alert_generator import build_alert_text
from iris.monitoring.browser_tab_monitor import BrowserTabMonitor
from iris.monitoring.extension_server import start_extension_server
from iris.monitoring.models import StatusCategory, TargetType
from iris.monitoring.state_detector import detect_state
from iris.monitoring.terminal_log_collector import TerminalLogRegistry
from iris.monitoring import windows_event_collector

if TYPE_CHECKING:
    from iris.ai.gemma_client import GemmaClient
    from iris.monitoring.notification_policy import NotificationPolicy
    from iris.storage.database import Database


class MonitorManager(QObject):
    """Qt 시그널로 UI·어시스턴트에 알림."""

    # title, message, category, target_id, focus_hint, recommended_action, event_id
    alert_emitted = pyqtSignal(str, str, str, int, str, str, int)
    targets_changed = pyqtSignal()

    def __init__(
        self,
        settings: Settings,
        db: "Database",
        gemma: Optional["GemmaClient"],
        terminal_registry: TerminalLogRegistry,
        browser_monitor: BrowserTabMonitor,
        notification_policy: Optional["NotificationPolicy"] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._db = db
        self._gemma = gemma
        self._terminal_registry = terminal_registry
        self._browser = browser_monitor
        from iris.monitoring.notification_policy import NotificationPolicy as _NP

        self._notif_policy = notification_policy or _NP(
            db, default_cooldown_seconds=float(settings.monitor_interval_seconds) * 30 or 90.0
        )
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._http_server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        if not self._settings.enable_monitoring:
            return
        self._db.ensure_current_screen_target()
        self._db.ensure_system_log_target()
        self._start_http()
        sec = max(1, int(self._settings.monitor_interval_seconds))
        self._timer.start(sec * 1000)

    def stop(self) -> None:
        self._timer.stop()
        if self._http_server:
            srv = self._http_server
            self._http_server = None

            def _shutdown() -> None:
                try:
                    srv.shutdown()
                except Exception:
                    pass

            threading.Thread(target=_shutdown, daemon=True).start()

    def _start_http(self) -> None:
        if self._http_server is not None:
            return

        def on_payload(data: dict) -> None:
            tab_id = int(data.get("tabId") or data.get("tab_id") or 0)
            title = str(data.get("title") or "")
            url = str(data.get("url") or "")
            vtext = str(data.get("visibleText") or data.get("visible_text") or "")
            if tab_id <= 0:
                return
            if self._browser.ingest(tab_id, title, url, vtext):
                self._db.upsert_browser_tab_target(url, title)

        try:
            self._http_server, _ = start_extension_server(
                self._settings.iris_extension_host,
                self._settings.iris_extension_port,
                self._settings.iris_extension_token,
                on_payload,
            )
        except OSError:
            self._http_server = None

    def refresh_now(self) -> None:
        """수동 한 번 갱신."""
        self._on_tick()

    def _on_tick(self) -> None:
        if not self._settings.enable_monitoring:
            return
        rows = self._db.list_targets(True)
        for row in rows:
            self._process_target_row(row)
        self.targets_changed.emit()

    def _process_target_row(self, row) -> None:  # sqlite3.Row
        tid = int(row["id"])
        try:
            ttype = TargetType(row["type"])
        except ValueError:
            ttype = TargetType.DESKTOP_WINDOW
        title = row["title"] or ""
        process_name = row["process_name"] or ""
        url = row["url"] or ""

        snippet = ""
        if ttype == TargetType.TERMINAL_COMMAND:
            snippet = self._terminal_registry.snippet_for(tid)
        elif ttype == TargetType.DESKTOP_WINDOW:
            snippet = desktop_window_monitor.collect_for_target_row(
                self._settings, title, process_name
            )
        elif ttype == TargetType.BROWSER_TAB:
            snippet = self._browser.text_for_url_prefix(url) or self._browser.combined_text()
        elif ttype == TargetType.CURRENT_SCREEN:
            cap = screen_capture.capture_full_screen(self._settings)
            if cap:
                raw = ocr_engine.ocr_image(self._settings, cap)
                snippet, _ = ocr_engine.ocr_for_storage(self._settings, raw)
        elif ttype == TargetType.SYSTEM_LOG:
            evs = windows_event_collector.collect_recent_errors(6)
            snippet = windows_event_collector.format_for_detector(evs)

        snippet = (snippet or "")[:8000]
        h = hashlib.sha256(snippet.encode("utf-8", errors="replace")).hexdigest()
        ts = datetime.utcnow().isoformat()
        prev = self._db.get_recent_target_state(tid)
        prev_hash = str(prev["last_text_hash"]) if prev else ""
        prev_cat = StatusCategory.UNKNOWN
        if prev:
            try:
                prev_cat = StatusCategory(str(prev["status"]))
            except ValueError:
                prev_cat = StatusCategory.UNKNOWN
        prev_changed_iso = str(prev["last_changed_at"]) if prev and prev["last_changed_at"] else None
        if prev_hash == h and prev_changed_iso:
            last_changed_iso = prev_changed_iso
        else:
            last_changed_iso = ts

        res = detect_state(
            ttype,
            snippet,
            prev_cat,
            prev_hash,
            h,
            last_changed_iso,
            stall_seconds=float(self._settings.monitor_stall_seconds),
        )

        self._db.upsert_recent_target_state(
            tid,
            res.category,
            h,
            last_changed_iso,
            ts,
        )
        display = (res.recommended_action or res.reason)[:480]
        self._db.update_target_runtime(tid, res.category, display, ts)

        if res.category not in (StatusCategory.NORMAL, StatusCategory.UNKNOWN):
            if res.category != prev_cat:
                cat_val = res.category.value
                suppress = self._notif_policy.should_suppress(tid, cat_val)
                if suppress:
                    self._db.insert_log(
                        "monitor",
                        f"alert_suppressed:{suppress}",
                        f"target={tid} cat={cat_val}",
                    )
                    return
                eid = self._db.insert_event(
                    tid,
                    title,
                    res.category,
                    res.confidence,
                    res.reason[:1000],
                    res.recommended_action[:1000],
                )
                msg = build_alert_text(self._gemma, res, title)
                focus = title or process_name or "Chrome"
                self._notif_policy.mark_shown(tid, cat_val)
                self._notif_policy.log_notification(
                    tid, eid, cat_val, title, msg[:500], "shown"
                )
                self.alert_emitted.emit(
                    title,
                    msg,
                    cat_val,
                    tid,
                    focus,
                    res.recommended_action,
                    eid,
                )
