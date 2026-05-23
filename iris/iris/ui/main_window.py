"""메인 PyQt6 창."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QCloseEvent, QPalette
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSplitter, QVBoxLayout, QWidget

from iris.agent.report_window import ReportWindow
from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.external_agent_adapter import external_backend_status_line
from iris.agent.needs_agent import format_hits_for_gemma_context
from iris.assistant.tool_layer import is_search_intent
from iris.automation.action_executor import ActionExecutor
from iris.audio.barge_in import BargeInController
from iris.audio.continuous_listen import ContinuousListenController
from iris.audio.speech_formatter import format_speech, infer_speech_tone
from iris.audio.stt_engine import SttEngine
from iris.audio.tts_engine import TtsEngine
from iris.audio.tts_manager import TtsStatus
from iris.audio.voice_gate import VoiceCommandGate
from iris.config.app_index import build_merged_app_paths
from iris.config.app_install_watcher import AppInstallWatcher
from iris.config.env_store import update_env_values
from iris.config.settings import load_settings
from iris.core.activity_sink import push_activity_line, register_activity_sink
from iris.core.command_router import CommandKind
from iris.core.intent_router import route_user_intent
from iris.core.context_manager import PendingMonitoringAction
from iris.core.state_machine import AppState, StateMachine
from iris.monitoring import BrowserTabMonitor, MonitorManager, TerminalLogRegistry
from iris.monitoring.dialogue_bridge import monitoring_proposal_message
from iris.monitoring.notification_policy import NotificationPolicy
from iris.monitoring.target_registry import TargetRegistry
from iris.memory.memory_manager import commit_turn_pair, strip_iris_prefix
from iris.storage.database import Database
from iris.ui.chat_panel import ChatPanel
from iris.ui.drag_tab import DragTab
from iris.ui.live_activity_panel import LiveActivityPanel, UiActivityRelay
from iris.ui.notification_panel import NotificationPanel
from iris.ui.settings_dialog import SettingsDialog
from iris.ui.bridge_signals import UiBridge
from iris.ui.visualizer import Visualizer
from iris.ui.unified_monitor_panel import UnifiedMonitorPanel
from iris.ui.window_list_panel import WindowListPanel
from iris.ui.workers import AgentWorker, AppLauncherScanWorker, LlmWorker, SearchWorker


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
        QFrame#StatusHeader {
            background-color: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 8px;
        }
        QFrame#WorkspacePanel {
            background-color: #0b1220;
            border: none;
        }
        QLabel#StatusPill {
            background-color: #111827;
            border: 1px solid #243247;
            border-radius: 7px;
            padding: 5px 9px;
            color: #cbd5e1;
        }
        QLabel#BackendStatus { color: #dbeafe; }
        QLabel#TtsStatus { color: #cbd5e1; }
        QSplitter::handle {
            background-color: #111827;
            margin: 8px 2px;
            border-radius: 2px;
        }
        QLabel#DragTitle { font-weight: 700; font-size: 16px; color: #c4b5fd; }
        QLabel#PanelTitle { font-weight: 600; color: #93c5fd; }
        QLabel#ModelStatus { color: #a5b4fc; font-weight: 600; }
        """
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Iris")
        self.setMinimumSize(1100, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        self._settings = load_settings(self._env_path)
        self._db = Database()
        self._targets = TargetRegistry(self._db)
        self._term_log = TerminalLogRegistry()
        self._browser = BrowserTabMonitor()
        self._app_paths = build_merged_app_paths(self._db)
        self._executor = ActionExecutor(
            self._db,
            self._app_paths,
            register_target=lambda k, h: self._targets.register(k, h),
            settings=self._settings,
        )
        self._gemma = GemmaClient(self._settings)
        self._assistant = IrisAssistant(
            self._db, self._executor, self._gemma, self._app_paths, self._settings
        )
        self._install_watcher = AppInstallWatcher(self)
        self._install_watcher.install_complete.connect(self._on_install_complete)
        self._maybe_run_initial_app_scan()
        self._stt = SttEngine(self._settings)
        self._tts = TtsEngine(self._settings, parent=self)
        self._tts.status_changed.connect(self._on_tts_status_changed)
        self._bridge = UiBridge(self)
        self._bridge.barge_in.connect(self._barge_slot)
        self._bridge.tts_finished.connect(self._tts_done_slot)
        self._barge = BargeInController(
            self._tts,
            ui_hook=lambda: self._bridge.barge_in.emit(),
            input_device=self._settings.always_listen_input_device,
        )
        self._continuous_listen = ContinuousListenController(self._settings, self._stt, self)
        self._continuous_listen.utterance_ready.connect(self._on_voice_utterance)
        self._continuous_listen.listen_failed.connect(self._on_listen_failed)
        self._continuous_listen.speech_started.connect(self._on_speech_started)
        self._continuous_listen.stt_started.connect(self._on_stt_started)
        self._continuous_listen.utterance_failed.connect(self._on_utterance_failed)
        self._voice_gate = VoiceCommandGate(
            wake_words=self._settings.voice_wake_words,
            require_wake_word=self._settings.voice_require_wake_word,
            followup_seconds=self._settings.voice_followup_seconds,
        )
        self._state = StateMachine()
        self._state.state_changed.connect(self._on_state_changed)

        self._history: list[ChatMessage] = []
        self._report = ReportWindow(self)
        self._llm_worker: LlmWorker | None = None
        self._search_worker: SearchWorker | None = None
        self._agent_worker: AgentWorker | None = None
        self._last_user_text = ""
        # Phase 2: early_ack TTS 완료 후 follow-up TTS (워커 스레드 블로킹 없음)
        self._pending_final: tuple[str, str, bool] | None = None
        self._early_ack_tts_done = True
        self._final_reply_received = False
        self._skip_followup_tts = False

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        self._drag = DragTab(self)
        self._drag.settings_clicked.connect(self._open_settings_dialog)
        root.addWidget(self._drag)

        status_header = QFrame()
        status_header.setObjectName("StatusHeader")
        status_header_lay = QVBoxLayout(status_header)
        status_header_lay.setContentsMargins(12, 10, 12, 10)
        status_header_lay.setSpacing(8)
        status_top = QHBoxLayout()
        status_top.setContentsMargins(0, 0, 0, 0)
        status_top.setSpacing(8)

        self._model_label = QLabel()
        self._model_label.setObjectName("ModelStatus")
        self._refresh_model_label()
        status_top.addWidget(self._model_label)
        status_top.addStretch(1)

        self._status_label = QLabel("상태: IDLE")
        self._status_label.setObjectName("StatusPill")
        status_top.addWidget(self._status_label)
        self._tts_status_label = QLabel(self._tts.status_label)
        self._tts_status_label.setObjectName("TtsStatus")
        status_top.addWidget(self._tts_status_label)
        status_header_lay.addLayout(status_top)
        self._backend_status = QLabel(external_backend_status_line(self._settings))
        self._backend_status.setObjectName("BackendStatus")
        self._backend_status.setWordWrap(True)
        status_header_lay.addWidget(self._backend_status)
        root.addWidget(status_header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        # 좌측 통합 사이드바 — 실행 중인 창 목록
        self._window_sidebar = WindowListPanel()
        splitter.addWidget(self._window_sidebar)

        left = QWidget()
        left.setObjectName("WorkspacePanel")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)
        self._viz = Visualizer()
        self._viz.setMinimumHeight(300)
        self._continuous_listen.mic_level.connect(self._viz.set_mic_level)
        left_lay.addWidget(self._viz, 1)

        self._activity_relay = UiActivityRelay(self)
        self._live_activity = LiveActivityPanel(self)
        self._activity_relay.line.connect(self._live_activity.enqueue_typed_line)
        register_activity_sink(self._activity_relay.push)
        left_lay.addWidget(self._live_activity)

        if os.environ.get("IRIS_DEBUG_PARTICLE") == "1":
            dbg = QWidget()
            dbg_row = QHBoxLayout(dbg)
            dbg_row.setContentsMargins(0, 4, 0, 0)
            for st in (
                AppState.IDLE,
                AppState.LISTENING,
                AppState.PROCESSING,
                AppState.RESPONDING,
                AppState.ALERTING,
            ):
                btn = QPushButton(st.name)
                btn.clicked.connect(lambda _checked=False, s=st: self._state.set_state(s))
                dbg_row.addWidget(btn)
            dbg_row.addStretch(1)
            left_lay.addWidget(dbg)
        self._chat = ChatPanel()
        self._chat.set_speech_threshold_rms(self._settings.always_listen_speech_rms)
        self._continuous_listen.mic_level.connect(self._chat.set_mic_level)
        left_lay.addWidget(self._chat, 2)
        splitter.addWidget(left)

        right = QWidget()
        right.setObjectName("WorkspacePanel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        # 실행 화면 + 모니터링 통합 (세로 1열)
        self._monitor = UnifiedMonitorPanel()
        self._monitor.set_database(self._db)

        self._notif_policy = NotificationPolicy(self._db)
        self._notes = NotificationPanel(policy=self._notif_policy)
        rl.addWidget(self._monitor, 2)
        rl.addWidget(self._notes, 1)
        splitter.addWidget(right)
        # [사이드바 | 메인 좌측 | 우측 모니터]
        splitter.setSizes([230, 760, 390])
        splitter.setCollapsible(0, False)  # 사이드바는 접히지 않도록

        root.addWidget(splitter, 1)

        self.setCentralWidget(central)
        _apply_dark_theme(self)

        self._chat.send_clicked.connect(lambda t: self._on_user_text(t, from_voice=False))
        if self._settings.always_listen_enabled:
            self._continuous_listen.start()
            self._notes.add_note("상시 음성 대기: 말씀하시면 인식합니다.")
        self._warmup_stt_async()

        self._monitor_mgr = MonitorManager(
            self._settings,
            self._db,
            self._gemma,
            self._term_log,
            self._browser,
            notification_policy=self._notif_policy,
            parent=self,
        )
        self._monitor_mgr.alert_emitted.connect(self._on_monitor_alert)
        self._monitor_mgr.targets_changed.connect(self._on_targets_changed)
        self._monitor_mgr.start()

        act_quit = QAction("종료", self)
        act_quit.triggered.connect(self.close)
        self.addAction(act_quit)

        # 전체화면(최대화)으로 시작
        self.showMaximized()

    def _warmup_stt_async(self) -> None:
        """Whisper 모델 선로딩 — 첫 음성 인식 지연 완화."""
        import threading

        if not self._settings.use_whisper:
            return
        threading.Thread(
            target=self._stt.warmup,
            name="iris-stt-warmup",
            daemon=True,
        ).start()

    def _rebuild_voice_input(self) -> None:
        """마이크 설정 변경 후 음성 입력 컨트롤러를 재구성한다."""
        self._continuous_listen.stop()
        self._stt = SttEngine(self._settings)
        self._barge = BargeInController(
            self._tts,
            ui_hook=lambda: self._bridge.barge_in.emit(),
            input_device=self._settings.always_listen_input_device,
        )
        self._continuous_listen = ContinuousListenController(self._settings, self._stt, self)
        self._continuous_listen.utterance_ready.connect(self._on_voice_utterance)
        self._continuous_listen.listen_failed.connect(self._on_listen_failed)
        self._continuous_listen.speech_started.connect(self._on_speech_started)
        self._continuous_listen.stt_started.connect(self._on_stt_started)
        self._continuous_listen.utterance_failed.connect(self._on_utterance_failed)
        self._continuous_listen.mic_level.connect(self._viz.set_mic_level)
        self._continuous_listen.mic_level.connect(self._chat.set_mic_level)
        self._voice_gate = VoiceCommandGate(
            wake_words=self._settings.voice_wake_words,
            require_wake_word=self._settings.voice_require_wake_word,
            followup_seconds=self._settings.voice_followup_seconds,
        )
        if self._settings.always_listen_enabled:
            self._continuous_listen.start()
        self._warmup_stt_async()

    def _model_status_line(self) -> str:
        """현재 LLM 모델 태그 (예: 모델: gemma4:e4b)."""
        if not self._settings.use_local_llm:
            return "모델: (로컬 LLM 비활성)"
        name = self._settings.gemma_model_name.strip()
        return f"모델: {name}" if name else "모델: (미설정)"

    def _refresh_model_label(self) -> None:
        self._model_label.setText(self._model_status_line())

    def _refresh_app_paths(self) -> None:
        """DB 인덱스 + detect 병합 후 executor·assistant에 반영."""
        merged = build_merged_app_paths(self._db)
        self._app_paths.clear()
        self._app_paths.update(merged)
        self._executor.update_app_paths(self._app_paths)
        self._assistant.update_app_paths(self._app_paths)

    def _maybe_run_initial_app_scan(self) -> None:
        """첫 실행 1회만 백그라운드 스캔 (24h 주기 타이머 없음)."""
        if self._db.get_preference("app_launcher_initial_scan_done", "0") in ("1", "true", "True"):
            return
        worker = AppLauncherScanWorker(self._db, parent=self)
        worker.finished_scan.connect(self._on_initial_app_scan_done)
        worker.start()
        self._initial_scan_worker = worker

    @pyqtSlot(int, list)
    def _on_initial_app_scan_done(self, _new_count: int, _names: list) -> None:
        self._db.set_preference("app_launcher_initial_scan_done", "1")
        self._refresh_app_paths()

    @pyqtSlot(str, str, str)
    def _on_install_complete(self, app_key: str, display_name: str, exe_path: str) -> None:
        row = self._db.get_app_launcher_entry(app_key)
        if row and str(row["exe_path"]) == exe_path:
            return
        self._db.upsert_app_launcher_entry(app_key, display_name, exe_path, "install_watch")
        self._refresh_app_paths()
        self._notes.add_note(f"앱 런처: {display_name} 자동 등록")

    def _apply_runtime_settings(self) -> None:
        """저장된 설정을 현재 세션에 반영한다."""
        self._settings = load_settings(self._env_path)
        self._gemma = GemmaClient(self._settings)
        self._refresh_app_paths()
        self._assistant = IrisAssistant(
            self._db, self._executor, self._gemma, self._app_paths, self._settings
        )
        self._chat.set_speech_threshold_rms(self._settings.always_listen_speech_rms)
        self._rebuild_voice_input()
        self._refresh_model_label()
        think_label = {
            "off": "사용 안 함",
            "default": "기본",
            "on": "항상 사용",
        }.get(self._settings.thinking_mode, self._settings.thinking_mode)
        self._notes.add_note(
            f"설정 적용: 모델={self._settings.gemma_model_name}, "
            f"마이크={self._settings.always_listen_input_device}, "
            f"LLM 추론={think_label}"
        )

    def _open_settings_dialog(self) -> None:
        # 설정창 마이크 미리보기와 상시 듣기가 동시에 같은 장치를 잡지 않도록
        resume_listen = self._settings.always_listen_enabled
        self._continuous_listen.stop()
        dlg = SettingsDialog(
            self._settings,
            self,
            db=self._db,
            on_app_paths_changed=self._refresh_app_paths,
        )
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            if resume_listen:
                self._continuous_listen.start()
            return
        selection = dlg.selection()
        update_env_values(
            self._env_path,
            {
                "GEMMA_MODEL_NAME": selection.model_name,
                "AI_MODEL_NAMES": ",".join(selection.model_names),
                "ALWAYS_LISTEN_INPUT_DEVICE": (
                    str(selection.input_device) if selection.input_device is not None else None
                ),
                "ALWAYS_LISTEN_SPEECH_RMS": f"{selection.speech_rms:.4f}",
                "DEFAULT_WEB_BROWSER": selection.default_web_browser,
                "IRIS_THINKING_MODE": selection.thinking_mode,
            },
        )
        self._apply_runtime_settings()

    @pyqtSlot()
    def _barge_slot(self) -> None:
        self._state.set_state(AppState.LISTENING)
        if self._settings.barge_in_enabled:
            self._notes.add_note("Barge-in: 음성 감지로 TTS 중단")
        # early_ack/follow-up 턴 중 끼어들기 → follow-up TTS 스킵, 새 입력 우선
        if not self._early_ack_tts_done or self._pending_final is not None:
            self._skip_followup_tts = True
            self._pending_final = None
            self._final_reply_received = False
            self._early_ack_tts_done = True

    @pyqtSlot()
    def _tts_done_slot(self) -> None:
        self._state.reset_to_idle()
        self._resume_voice_input()

    @pyqtSlot()
    def _on_targets_changed(self) -> None:
        self._monitor.refresh_now()

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
        self._notes.try_add_alert(
            target_id, category, title, message, focus_hint, event_id=event_id
        )
        proposal = monitoring_proposal_message(category, title, recommended, message)
        self._assistant.memory.add_long_term_summary(
            "monitor", proposal[:240], source_hint=title[:80]
        )
        self._assistant.memory.save_task_session(
            current_goal=f"모니터링: {title}",
            observations=[proposal[:200]],
        )
        if category in (
            "APPROVAL_WAITING",
            "ERROR_DETECTED",
            "TASK_STALLED",
            "RESPONSE_READY",
            "USER_ACTION_REQUIRED",
            "GENERATION_FAILED",
        ):
            self._chat.append_message("Iris", proposal)
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
                natural_language=proposal,
            )
            if self._assistant.set_monitor_pending(pm):
                pass  # proposal already in chat

    def _on_state_changed(self, s: object) -> None:
        if isinstance(s, AppState):
            self._viz.set_state(s)
            self._status_label.setText(f"상태: {s.name}")
            push_activity_line(f"UI: app state → {s.name}.")
            self._backend_status.setText(external_backend_status_line(self._settings))

    def _pause_voice_input(self) -> None:
        if self._settings.always_listen_enabled:
            self._continuous_listen.pause()

    def _resume_voice_input(self) -> None:
        if self._settings.always_listen_enabled and self._state.state not in (
            AppState.PROCESSING,
            AppState.EXECUTING,
            AppState.RESPONDING,
        ):
            self._continuous_listen.resume()

    @pyqtSlot()
    def _on_speech_started(self) -> None:
        if self._state.state in (AppState.PROCESSING, AppState.EXECUTING, AppState.RESPONDING):
            return
        push_activity_line("Mic: speech segment started (listening).")
        self._chat.begin_user_listening()
        if self._state.state == AppState.IDLE:
            self._state.set_state(AppState.LISTENING)

    @pyqtSlot()
    def _on_stt_started(self) -> None:
        push_activity_line("STT: stream decode started (silence-boundary).")
        self._chat.set_user_listening_status("인식 중…")

    @pyqtSlot()
    def _on_utterance_failed(self) -> None:
        push_activity_line("STT: utterance empty — no usable transcript.")
        self._chat.cancel_user_listening()
        self._chat.append_message(
            "Iris",
            "음성을 인식하지 못했습니다. 조용한 환경에서 다시 말씀해 주세요.",
        )
        self._state.reset_to_idle()
        self._resume_voice_input()

    @pyqtSlot(str)
    def _on_listen_failed(self, message: str) -> None:
        # 상시 대기 중 인식 실패는 조용히 무시 (텍스트 입력 가능)
        if "음성을 인식하지 못했습니다" in message:
            return
        self._notes.add_note(message)

    @pyqtSlot(str)
    def _on_voice_utterance(self, text: str) -> None:
        push_activity_line("STT: utterance ready (accepted for gating pipeline).")
        if self._state.state in (AppState.PROCESSING, AppState.EXECUTING, AppState.RESPONDING):
            self._chat.cancel_user_listening()
            return
        gated = self._voice_gate.filter(text)
        if not gated.accepted:
            self._chat.cancel_user_listening()
            if gated.reject_reason == "wake_word":
                self._chat.append_message(
                    "Iris",
                    f"호출어를 인식하지 못했습니다 (들린 내용: 「{text[:40]}」). "
                    "「아이리스」 또는 「iris」로 불러 주세요.",
                )
            self._state.reset_to_idle()
            self._resume_voice_input()
            return
        if gated.prompt_only:
            self._chat.cancel_user_listening()
            self._chat.append_message_typed("Iris", "네, 말씀하세요.")
            self._speak("네, 말씀하세요.")
            return
        self._pause_voice_input()
        self._chat.complete_user_message_typed(gated.command_text)
        self._on_user_text(gated.command_text, from_voice=True, already_shown=True)

    @pyqtSlot(object)
    def _on_tts_status_changed(self, _status: object) -> None:
        self._tts_status_label.setText(self._tts.status_label)
        if isinstance(_status, TtsStatus) and _status is TtsStatus.TTS_ERROR:
            notice = getattr(self._tts, "_last_user_notice", None)
            if notice:
                self._notes.add_note(notice)

    def _speak(self, text: str, *, on_complete: object | None = None) -> None:
        def on_synthesis_start() -> None:
            self._state.set_state(AppState.PROCESSING)

        def on_playback_start() -> None:
            self._state.set_state(AppState.RESPONDING)
            self._pause_voice_input()
            if self._settings.barge_in_enabled:
                self._barge.notify_tts_started()
                self._barge.start_listening()

        def on_done() -> None:
            if callable(on_complete):
                on_complete()
            else:
                self._bridge.tts_finished.emit()

        self._tts.speak(
            text,
            on_synthesis_start=on_synthesis_start,
            on_playback_start=on_playback_start,
            on_done=on_done,
        )

    def _on_user_text(
        self,
        text: str,
        *,
        from_voice: bool = False,
        already_shown: bool = False,
    ) -> None:
        text = text.strip()
        if not text:
            if from_voice:
                self._chat.cancel_user_listening()
            self._resume_voice_input()
            return
        self._pause_voice_input()
        self._state.set_state(AppState.LISTENING)
        if not already_shown:
            if from_voice:
                self._chat.complete_user_message_typed(text)
            else:
                self._chat.append_message("나", text)
        # 진행 중 턴은 memory에 넣지 않음 — 턴 완료 시 user+assistant 한꺼번에 커밋
        self._db.insert_log("user", text, None)
        push_activity_line(
            f"UI: user turn submitted ({'voice' if from_voice else 'text'}), log row written."
        )
        self._state.set_state(AppState.PROCESSING)
        self._last_user_text = text
        self._pending_final = None
        self._skip_followup_tts = False
        self._early_ack_tts_done = True
        self._final_reply_received = False
        self._start_agent_worker(text)

    def _start_agent_worker(self, text: str) -> None:
        """승인·Agent loop·검색 위임 — 백그라운드 스레드."""
        if self._agent_worker and self._agent_worker.isRunning():
            self._agent_worker.requestInterruption()
        self._agent_worker = AgentWorker(self._assistant, text)
        self._agent_worker.finished_reply.connect(self._on_agent_worker_reply)
        self._agent_worker.delegate_search.connect(self._on_agent_delegate_search)
        self._agent_worker.early_ack.connect(
            self._on_agent_early_ack,
            Qt.ConnectionType.QueuedConnection,
        )
        self._agent_worker.start()

    @pyqtSlot(str)
    def _on_agent_early_ack(self, ack: str) -> None:
        """DIRECT_ACTION 실행 전 짧은 확인 — 즉시 채팅·TTS."""
        self._early_ack_tts_done = False
        self._final_reply_received = False
        self._skip_followup_tts = False
        self._db.insert_log("assistant_early_ack", ack, None)
        self._chat.append_message_typed("Iris", ack)
        tone = infer_speech_tone(from_llm=False, reply_text=ack)
        if self._settings.tts_enable_speech_formatter:
            spoken = format_speech(
                ack,
                tone,
                max_sentences=min(2, self._settings.tts_max_spoken_sentences),
            )
        else:
            spoken = ack
        self._speak(spoken, on_complete=self._on_early_ack_tts_done)

    def _on_early_ack_tts_done(self) -> None:
        """ack TTS 종료 — 워커 실행 중이면 EXECUTING, follow-up 대기."""
        self._early_ack_tts_done = True
        if not self._final_reply_received:
            self._state.set_state(AppState.EXECUTING)
        self._try_deliver_final_reply()

    def _try_deliver_final_reply(self) -> None:
        if not self._final_reply_received or not self._early_ack_tts_done:
            return
        if self._pending_final is None:
            return
        user_visible, spoken_followup, store_history = self._pending_final
        self._pending_final = None
        self._final_reply_received = False

        if self._skip_followup_tts:
            self._db.insert_log("assistant", user_visible, None)
            self._commit_completed_turn(user_visible, store_history=store_history)
            self._state.reset_to_idle()
            self._resume_voice_input()
            return

        if spoken_followup.strip():
            self._chat.append_message_typed("Iris", spoken_followup)

        self._db.insert_log("assistant", user_visible, None)
        self._commit_completed_turn(user_visible, store_history=store_history)

        if spoken_followup.strip():
            tone = infer_speech_tone(from_llm=False, reply_text=spoken_followup)
            if self._settings.tts_enable_speech_formatter:
                spoken = format_speech(
                    spoken_followup,
                    tone,
                    max_sentences=self._settings.tts_max_spoken_sentences,
                )
            else:
                spoken = spoken_followup
            self._speak(spoken)
        else:
            self._bridge.tts_finished.emit()

    @pyqtSlot(str, bool, bool, str)
    def _on_agent_worker_reply(
        self,
        reply: str,
        store_history: bool,
        had_early_ack: bool,
        spoken_followup: str,
    ) -> None:
        if had_early_ack:
            self._pending_final = (reply, spoken_followup, store_history)
            self._final_reply_received = True
            self._try_deliver_final_reply()
            return
        self._finish_assistant_reply(reply, store_history=store_history)

    @pyqtSlot(str, str, str)
    def _on_agent_delegate_search(
        self, text: str, intent_name: str, slot_query: str = ""
    ) -> None:
        try:
            intent = CommandKind[intent_name]
        except KeyError:
            intent = CommandKind.WEB_SEARCH
        sq = slot_query.strip() or None
        self._start_search_worker(text, intent, slot_query=sq)

    def _start_search_worker(
        self,
        text: str,
        intent: CommandKind,
        *,
        slot_query: str | None = None,
    ) -> None:
        self._search_worker = SearchWorker(text, intent=intent, slot_query=slot_query)
        self._search_worker.finished_hits.connect(self._on_search_done)
        self._search_worker.start()

    def _on_search_done(self, query: str, hits: object, intent_name: str) -> None:
        push_activity_line(
            f"UI: search worker returned intent={intent_name!r} hit_count={len(hits)}."
        )
        self._report.set_hits(query, hits)  # type: ignore[arg-type]
        self._report.show()
        try:
            intent = CommandKind[intent_name]
        except KeyError:
            intent = CommandKind.WEB_SEARCH
        self._db.insert_log("web", query, f"hits={len(hits)} intent={intent.name}")  # type: ignore[arg-type]
        ctx = format_hits_for_gemma_context(
            query,
            hits,  # type: ignore[arg-type]
            intent_label=intent.name,
        )
        messages = self._assistant.build_general_chat_messages(
            self._last_user_text,
            history=self._history[-8:],
            extra_context=ctx,
        )
        self._llm_worker = LlmWorker(self._assistant.gemma_client, messages)
        push_activity_line("UI: summarization LlmWorker starting with search context.")
        self._llm_worker.finished_text.connect(self._on_llm_done)
        self._llm_worker.start()

    def _on_llm_done(self, text: str) -> None:
        self._finish_assistant_reply(text, store_history=True)

    def _commit_completed_turn(self, assistant_visible: str, *, store_history: bool) -> None:
        """턴 성공 시에만 user+assistant를 memory·_history에 커밋 (Iris: 접두어 제외)."""
        if not store_history:
            return
        user = (self._last_user_text or "").strip()
        if not user:
            return
        body = strip_iris_prefix(assistant_visible)
        if commit_turn_pair(self._assistant.memory, user, assistant_visible):
            self._history.append(ChatMessage("user", user))
            self._history.append(ChatMessage("assistant", body))

    def _finish_assistant_reply(self, text: str, store_history: bool) -> None:
        self._chat.append_message_typed("Iris", text)
        self._db.insert_log("assistant", text, None)
        self._commit_completed_turn(text, store_history=store_history)
        tone = infer_speech_tone(from_llm=store_history, reply_text=text)
        if self._settings.tts_enable_speech_formatter:
            spoken = format_speech(
                text,
                tone,
                max_sentences=self._settings.tts_max_spoken_sentences,
            )
        else:
            spoken = text
        self._speak(spoken)

    def closeEvent(self, event: QCloseEvent) -> None:
        register_activity_sink(None)
        self._monitor_mgr.stop()
        self._continuous_listen.stop()
        self._tts.stop()
        self._barge.stop()
        self._db.close()
        event.accept()
