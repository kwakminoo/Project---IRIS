"""메인 PyQt6 창."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QCloseEvent, QPalette
from PyQt6.QtWidgets import QLabel, QMainWindow, QSplitter, QVBoxLayout, QWidget

from iris.agent.report_window import ReportWindow
from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.prompt_builder import build_messages
from iris.assistant.agent_adapter import IrisAssistant
from iris.automation.action_executor import ActionExecutor
from iris.audio.barge_in import BargeInController
from iris.audio.stt_engine import SttEngine
from iris.audio.tts_engine import TtsEngine
from iris.config.app_paths import detect_app_paths
from iris.config.settings import load_settings
from iris.core.command_router import CommandKind, classify_command
from iris.core.context_manager import PendingMonitoringAction
from iris.core.state_machine import AppState, StateMachine
from iris.monitoring import BrowserTabMonitor, MonitorManager, TerminalLogRegistry
from iris.monitoring.target_registry import TargetRegistry
from iris.storage.database import Database
from iris.ui.chat_panel import ChatPanel
from iris.ui.drag_tab import DragTab
from iris.ui.monitor_dashboard import MonitorDashboard
from iris.ui.notification_panel import NotificationPanel
from iris.ui.bridge_signals import UiBridge
from iris.ui.visualizer import Visualizer
from iris.ui.workers import LlmWorker, SearchWorker


def _apply_dark_theme(w: QWidget) -> None:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#0b1220"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#e2e8f0"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#111827"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#e2e8f0"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#1e293b"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#e2e8f0"))
    w.setPalette(pal)
    w.setStyleSheet(
        """
        QWidget { background-color: #0b1220; color: #e2e8f0; font-size: 13px; }
        QTextEdit, QListWidget, QLineEdit {
            background-color: #111827; border: 1px solid #334155; border-radius: 6px;
        }
        QPushButton {
            background-color: #312e81; color: #e0e7ff; border-radius: 6px; padding: 6px 12px;
        }
        QPushButton:hover { background-color: #4338ca; }
        QLabel#DragTitle { font-weight: 700; font-size: 16px; color: #c4b5fd; }
        QLabel#PanelTitle { font-weight: 600; color: #93c5fd; }
        """
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Iris")
        self.setMinimumSize(1100, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        self._settings = load_settings(env_path)
        self._db = Database()
        self._targets = TargetRegistry(self._db)
        self._term_log = TerminalLogRegistry()
        self._browser = BrowserTabMonitor()
        self._app_paths = detect_app_paths()
        self._executor = ActionExecutor(
            self._db,
            self._app_paths,
            register_target=lambda k, h: self._targets.register(k, h),
        )
        self._assistant = IrisAssistant(self._db, self._executor)
        self._gemma = GemmaClient(self._settings)
        self._stt = SttEngine(self._settings)
        self._tts = TtsEngine(self._settings)
        self._bridge = UiBridge(self)
        self._bridge.barge_in.connect(self._barge_slot)
        self._bridge.tts_finished.connect(self._tts_done_slot)
        self._barge = BargeInController(self._tts, ui_hook=lambda: self._bridge.barge_in.emit())
        self._state = StateMachine()
        self._state.state_changed.connect(self._on_state_changed)

        self._history: list[ChatMessage] = []
        self._report = ReportWindow(self)
        self._llm_worker: LlmWorker | None = None
        self._search_worker: SearchWorker | None = None
        self._last_user_text = ""

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)

        self._drag = DragTab(self)
        root.addWidget(self._drag)

        self._status_label = QLabel("상태: IDLE")
        root.addWidget(self._status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        self._viz = Visualizer()
        self._viz.setMinimumHeight(260)
        left_lay.addWidget(self._viz, 1)
        self._chat = ChatPanel()
        left_lay.addWidget(self._chat, 2)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self._monitor = MonitorDashboard()
        self._monitor.set_database(self._db)
        self._monitor.refresh_cards()
        self._notes = NotificationPanel()
        rl.addWidget(self._monitor, 1)
        rl.addWidget(self._notes, 1)
        splitter.addWidget(right)
        splitter.setSizes([720, 360])

        root.addWidget(splitter, 1)

        self.setCentralWidget(central)
        _apply_dark_theme(self)

        self._chat.send_clicked.connect(self._on_user_text)
        self._chat.listen_clicked.connect(self._on_listen)

        self._monitor_mgr = MonitorManager(
            self._settings,
            self._db,
            self._gemma,
            self._term_log,
            self._browser,
            self,
        )
        self._monitor_mgr.alert_emitted.connect(self._on_monitor_alert)
        self._monitor_mgr.targets_changed.connect(self._on_targets_changed)
        self._monitor_mgr.start()

        act_quit = QAction("종료", self)
        act_quit.triggered.connect(self.close)
        self.addAction(act_quit)

    @pyqtSlot()
    def _barge_slot(self) -> None:
        self._state.set_state(AppState.LISTENING)
        self._notes.add_note("Barge-in: 음성 감지로 TTS 중단")

    @pyqtSlot()
    def _tts_done_slot(self) -> None:
        self._state.reset_to_idle()

    @pyqtSlot()
    def _on_targets_changed(self) -> None:
        self._monitor.refresh_cards()

    @pyqtSlot(str, str, str, int, str, str, int)
    def _on_monitor_alert(
        self,
        title: str,
        message: str,
        category: str,
        target_id: int,
        focus_hint: str,
        recommended: str,
        event_id: int,
    ) -> None:
        self._notes.try_add_alert(target_id, category, title, message, focus_hint)
        if category in ("APPROVAL_WAITING", "USER_ACTION_REQUIRED"):
            sug = "y"
            if "n" in (recommended or "").lower() and "y" not in (recommended or "").lower():
                sug = ""
            pm = PendingMonitoringAction(
                event_id=event_id,
                target_id=target_id,
                focus_hint=focus_hint,
                suggested_input=sug,
                category=category,
            )
            if self._assistant.set_monitor_pending(pm):
                self._chat.append_message(
                    "Iris",
                    "모니터링: 창/터미널 조작이 필요합니다. 진행하려면 '승인', 취소는 '취소'라고 말씀해 주세요.",
                )

    def _on_state_changed(self, s: object) -> None:
        if isinstance(s, AppState):
            self._viz.set_state(s)
            self._status_label.setText(f"상태: {s.name}")

    def _speak(self, text: str) -> None:
        def on_start() -> None:
            self._state.set_state(AppState.RESPONDING)
            self._barge.notify_tts_started()
            self._barge.start_listening()

        self._tts.speak(text, on_start=on_start, on_done=lambda: self._bridge.tts_finished.emit())

    def _on_user_text(self, text: str) -> None:
        self._state.set_state(AppState.LISTENING)
        self._chat.append_message("나", text)
        self._db.insert_log("user", text, None)
        self._state.set_state(AppState.PROCESSING)
        self._last_user_text = text

        kind = classify_command(text)
        if kind is CommandKind.WEB_OR_REPORT:
            self._start_search_worker(text)
            return

        reply = self._assistant.handle_user_text(text)
        if reply:
            self._finish_assistant_reply(reply, store_history=False)
            return

        messages = build_messages(text, extra_context=None, history=self._history[-8:])
        self._llm_worker = LlmWorker(self._gemma, messages)
        self._llm_worker.finished_text.connect(self._on_llm_done)
        self._llm_worker.start()

    def _start_search_worker(self, text: str) -> None:
        self._search_worker = SearchWorker(text)
        self._search_worker.finished_hits.connect(self._on_search_done)
        self._search_worker.start()

    def _on_search_done(self, query: str, hits: object) -> None:
        self._report.set_hits(query, hits)  # type: ignore[arg-type]
        self._report.show()
        msg = f"Iris: '{query}' 검색 결과를 보고서 창에 표시했습니다."
        self._db.insert_log("web", query, f"hits={len(hits)}")  # type: ignore[arg-type]
        self._finish_assistant_reply(msg, store_history=False)

    def _on_llm_done(self, text: str) -> None:
        self._finish_assistant_reply(text, store_history=True)

    def _finish_assistant_reply(self, text: str, store_history: bool) -> None:
        self._chat.append_message("Iris", text)
        self._db.insert_log("assistant", text, None)
        if store_history:
            self._history.append(ChatMessage("user", self._last_user_text))
            self._history.append(ChatMessage("assistant", text))
        self._speak(text)

    def _on_listen(self) -> None:
        """짧은 마이크 녹음 후 STT (구조용)."""
        self._state.set_state(AppState.LISTENING)
        try:
            import sounddevice as sd
        except Exception:
            self._chat.append_message("Iris", "sounddevice 미설치로 음성 입력을 사용할 수 없습니다.")
            self._state.reset_to_idle()
            return
        sample_rate = 16000
        seconds = 2.5
        try:
            audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
            sd.wait()
            text = self._stt.transcribe_audio(audio[:, 0], sample_rate)
        except Exception as e:
            self._chat.append_message("Iris", f"녹음 실패: {e}")
            self._state.reset_to_idle()
            return
        if not text:
            self._chat.append_message("Iris", "음성을 인식하지 못했습니다.")
            self._state.reset_to_idle()
            return
        self._on_user_text(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._monitor_mgr.stop()
        self._barge.stop()
        self._db.close()
        event.accept()
