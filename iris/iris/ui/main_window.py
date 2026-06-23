"""메인 PyQt6 창."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QDateTime, QEvent, Qt, QThread, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.stream_sentence import find_first_sentence_end
from iris.assistant.agent_adapter import IrisAssistant
from iris.agent.needs_agent import (
    assess_research_quality,
    format_comparison_degraded_context,
    format_hits_for_gemma_context,
    format_hybrid_without_hits,
    format_search_degraded_context,
    resolve_answer_mode,
)
from iris.agent.search_providers import ResearchQuality
from iris.assistant.tool_layer import is_search_intent
from iris.automation.action_executor import ActionExecutor
from iris.audio.barge_in import BargeInMonitor
from iris.audio.continuous_listen import ContinuousListenController
from iris.audio.audio_duration import estimate_speech_duration_ms
from iris.audio.speech_formatter import format_speech, infer_speech_tone
from iris.audio.stt_engine import SttEngine
from iris.audio.system_sounds import SystemSoundPlayer
from iris.audio.tts_engine import TtsEngine
from iris.audio.tts_manager import TtsStatus
from iris.audio.voice_gate import VoiceCommandGate
from iris.audio.voice_session import VoiceSessionController, VoiceSessionState
from iris.config.app_index import build_merged_app_paths
from iris.config.app_install_watcher import AppInstallWatcher
from iris.config.env_store import update_env_values
from iris.config.settings import load_settings
from iris.core.activity_sink import push_activity_line, register_activity_sink
from iris.core.command_router import CommandKind
from iris.core.intent_router import route_user_intent
from iris.core.state_machine import AppState, StateMachine
from iris.assistant.dialogue_agent import DialogueAgent
from iris.monitoring import BrowserTabMonitor, MonitorManager, TerminalLogRegistry
from iris.monitoring.proactive_suggestion import dispatch_proactive_monitor_event
from iris.monitoring.notification_policy import NotificationPolicy
from iris.monitoring.target_registry import TargetRegistry
from iris.memory.memory_manager import commit_turn_pair, strip_iris_prefix
from iris.storage.database import Database
from iris.ui.chat_panel import ChatPanel
from iris.ui.drag_tab import DragTab
from iris.ui.frameless_chrome import FramelessShell, center_on_screen, suppress_native_window_border
from iris.ui.live_activity_panel import LiveActivityPanel, UiActivityRelay
from iris.ui.notification_panel import NotificationPanel
from iris.ui.settings_dialog import SettingsDialog
from iris.ui.user_profile_dialog import UserProfileDialog
from iris.ui.bridge_signals import UiBridge
from iris.ui.visualizer import Visualizer
from iris.ui.unified_monitor_panel import UnifiedMonitorPanel
from iris.infrastructure.ide.ide_backend_manager import (
    BackendStatus,
    IdeBackendManager,
    tail_backend_log,
)
from iris.infrastructure.ide.ide_backend_worker import IdeBackendWorker
from iris.infrastructure.ide.ide_bridge_client import IdeBridgeClient
from iris.infrastructure.ide.ide_env_recovery import recover_webengine
from iris.infrastructure.ide.ide_preflight import format_preflight_error, run_ide_preflight
from iris.infrastructure.ide.ide_workspace_resolver import _find_repo_root, resolve_ide_workspace
from iris.ui.ide.embedded_theia_view import TheiaViewState
from iris.ui.ide.ide_bridge_relay import IdeBridgeRelay
from iris.ui.ide.iris_webengine_page import tail_webengine_log
from iris.system.metrics_worker import MetricsWorker
from iris.ui.cyberspace_background import CyberspaceBackground
from iris.ui.cyberspace_theme import apply_cyberspace_theme
from iris.ui.theme_tokens import TOKENS
from iris.ui.left_sidebar_panel import LeftSidebarPanel
from iris.ui.email_window import EmailWindow
from iris.ui.top_status_header import TopStatusHeader
from iris.ui.workspaces.assistant_workspace_page import AssistantWorkspacePage
from iris.ui.workspaces.ide_workspace_page import IdeWorkspacePage
from iris.ui.workers import AgentWorker, AppLauncherScanWorker, LlmWorker, SearchWorker


class MainWindow(QMainWindow):
    def __init__(self, *, test_mode: bool = False) -> None:
        super().__init__()
        self._test_mode = test_mode
        self.setWindowTitle("Iris")
        self.setMinimumSize(960, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        self._settings = load_settings(self._env_path)
        if self._test_mode:
            test_db_dir = Path.cwd() / ".iris_test_tmp"
            test_db_dir.mkdir(parents=True, exist_ok=True)
            self._db = Database(test_db_dir / "main_window_test.db")
        else:
            self._db = Database()
        self._targets = TargetRegistry(self._db)
        self._term_log = TerminalLogRegistry()
        self._browser = BrowserTabMonitor()
        self._app_paths = {} if self._test_mode else build_merged_app_paths(self._db)
        self._executor = ActionExecutor(
            self._db,
            self._app_paths,
            register_target=lambda k, h: self._targets.register(k, h),
            settings=self._settings,
        )
        self._gemma = GemmaClient(
            self._settings,
            timeout_sec=self._settings.llm_timeout_seconds,
        )
        self._assistant = IrisAssistant(
            self._db, self._executor, self._gemma, self._app_paths, self._settings
        )
        self._dialogue = DialogueAgent(self._assistant, self._gemma)
        self._install_watcher = AppInstallWatcher(self)
        self._install_watcher.install_complete.connect(self._on_install_complete)
        if not self._test_mode:
            self._maybe_run_initial_app_scan()
        self._stt = SttEngine(self._settings)
        self._tts = TtsEngine(self._settings, parent=self)
        self._tts.status_changed.connect(self._on_tts_status_changed)
        self._bridge = UiBridge(self)
        self._bridge.barge_in.connect(self._barge_slot)
        self._bridge.tts_finished.connect(self._tts_done_slot)
        self._voice_gate = VoiceCommandGate(
            wake_words=self._settings.voice_wake_words,
            require_wake_word=self._settings.voice_require_wake_word,
            followup_seconds=self._settings.voice_followup_seconds,
        )
        self._voice_stt_reject_streak = 0
        self._init_voice_pipeline()
        self._state = StateMachine()
        self._state.state_changed.connect(self._on_state_changed)
        self._system_sounds = SystemSoundPlayer(self)

        self._history: list[ChatMessage] = []
        self._llm_worker: LlmWorker | None = None
        self._search_worker: SearchWorker | None = None
        self._agent_worker: AgentWorker | None = None
        self._last_user_text = ""
        # Phase 2: early_ack TTS 완료 후 follow-up TTS (워커 스레드 블로킹 없음)
        self._pending_final: tuple[str, str, bool] | None = None
        self._early_ack_tts_done = True
        self._final_reply_received = False
        self._skip_followup_tts = False
        # 스트리밍 DIALOGUE_CHAT — 첫 문장 TTS·후속 TTS 분리
        self._stream_buffer = ""
        self._stream_tts_first_done = False
        self._stream_tts_spoken_len = 0
        self._stream_store_history = False
        self._stream_reply_ready = False
        self._stream_add_iris_prefix = False
        self._stream_final_visible = ""
        self._workspace_mode: str = "assistant"
        self._assistant_splitter_state = b""
        self._ide_splitter_state = b""
        self._ide_backend = IdeBackendManager()
        self._ide_backend_thread: QThread | None = None
        self._ide_backend_worker: IdeBackendWorker | None = None
        self._ide_bridge = IdeBridgeClient()
        self._ide_bridge.start()
        self._ide_bridge_relay = IdeBridgeRelay(self)
        self._ide_bridge.set_editor_state_callback(self._ide_bridge_relay.push)
        self._ide_bridge_relay.editor_state_changed.connect(self._on_ide_editor_state_changed)

        central = CyberspaceBackground()
        self._cyberspace_bg = central
        self._viz = Visualizer(central)
        self._continuous_listen.mic_level.connect(self._viz.set_mic_level)

        ui_overlay = QWidget()
        ui_overlay.setObjectName("UiOverlay")
        self._ui_overlay = ui_overlay
        central.set_orb_layer(self._viz)
        central.set_ui_overlay(ui_overlay)

        root = QVBoxLayout(ui_overlay)
        root.setContentsMargins(
            TOKENS.spacing_lg,
            TOKENS.spacing_sm,
            TOKENS.spacing_lg,
            TOKENS.spacing_sm,
        )
        root.setSpacing(TOKENS.spacing_sm)

        self._drag = DragTab(self)
        self._drag.profile_clicked.connect(self._open_user_profile_dialog)
        self._drag.settings_clicked.connect(self._open_settings_dialog)
        self._drag.minimize_clicked.connect(self.showMinimized)
        self._drag.maximize_clicked.connect(self._toggle_maximize)
        root.addWidget(self._drag)

        status_header = TopStatusHeader()
        self._status_header = status_header
        self._status_strip = status_header
        self._ui_root_lay = root
        self._model_label = status_header.model_label
        self._refresh_model_label()
        self._status_label = status_header.status_label
        self._tts_status_label = status_header.tts_status_label
        self._tts_status_label.setText(self._tts.status_label)
        status_header.set_tts_status(self._tts.status_label)
        status_header.refresh_backend_status(self._settings)
        self._drag.place_status_rows(
            status_header.status_widget(),
            status_header.backend_row(),
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)
        self._workspace_splitter = splitter
        self._sidebar_split_size = 220

        # 좌측 Persistent Sidebar — workspace 전환과 무관하게 유지
        self._left_sidebar = LeftSidebarPanel()
        splitter.addWidget(self._left_sidebar)

        self._assistant_page = AssistantWorkspacePage()
        self._ide_page = IdeWorkspacePage()
        self._email_page = EmailWindow(self._db)
        self._workspace_stack = QStackedWidget()
        self._workspace_stack.addWidget(self._assistant_page)
        self._workspace_stack.addWidget(self._ide_page)
        self._workspace_stack.addWidget(self._email_page)
        splitter.addWidget(self._workspace_stack)

        left_lay = self._assistant_page.center_layout
        right_lay = self._assistant_page.right_layout

        # 구체는 전체 창 오버레이 — 레이아웃에는 투명 여백만 유지(이전 Visualizer 자리)
        self._orb_spacer = QWidget()
        self._orb_spacer.setObjectName("OrbLayoutSpacer")
        self._orb_spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._orb_spacer.setMinimumHeight(160)
        self._orb_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left_lay.addWidget(self._orb_spacer, 2)
        self._viz.set_orb_anchor(self._orb_spacer)
        self._viz.register_geometry_watch(
            self._orb_spacer,
            self._assistant_page.center_column,
            self._assistant_page,
            self._assistant_page.splitter,
            ui_overlay,
            central,
            self,
        )

        self._activity_relay = UiActivityRelay(self)
        self._live_activity = LiveActivityPanel(self)
        self._activity_relay.line.connect(self._live_activity.enqueue_typed_line)
        self._activity_relay.line.connect(self._ide_page.append_live_activity)
        register_activity_sink(self._activity_relay.push)
        left_lay.addWidget(self._live_activity, 0)

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
        left_lay.addWidget(self._chat, 3)

        self._monitor = UnifiedMonitorPanel()
        self._monitor.set_database(self._db)
        self._monitor.setMinimumHeight(160)

        self._notif_policy = NotificationPolicy(self._db)
        self._notes = NotificationPanel(policy=self._notif_policy)
        self._notes.setMinimumHeight(120)
        right_lay.addWidget(self._monitor, 2)
        right_lay.addWidget(self._notes, 1)

        # [사이드바 | workspace stack]
        splitter.setSizes([220, 1160])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)

        actions = self._left_sidebar.utility.actions
        actions.add_icon_action(
            action_id="ide",
            icon_kind="ide",
            tooltip="Iris IDE 작업공간으로 전환",
            callback=self._on_ide_toggle,
        )
        for action_id, icon_kind, tooltip in (
            ("email", "email", "이메일"),
            ("instagram", "instagram", "Instagram"),
            ("discord", "discord", "Discord"),
            ("kakao", "kakao", "카카오톡"),
            ("telegram", "telegram", "텔레그램"),
        ):
            callback = self.switch_to_email_workspace if action_id == "email" else None
            actions.add_icon_action(action_id=action_id, icon_kind=icon_kind, tooltip=tooltip, callback=callback)
        self._ide_page.theia_retry.connect(lambda: self._start_ide_backend_and_load(force_reload=True))
        self._ide_page.theia_back.connect(self.switch_to_assistant_workspace)
        self._email_page.back_requested.connect(self.switch_to_assistant_workspace)
        self._ide_page.theia_view_log.connect(self._show_ide_log)
        self._ide_page.theia.diagnose_requested.connect(self._run_ide_diagnose)
        self._ide_page.theia.recover_env_requested.connect(self._run_ide_env_recovery)
        self._ide_page.theia.ready.connect(self._on_theia_ready)
        self._ide_page.coding_send_clicked.connect(self._on_coding_user_text)
        self._continuous_listen.mic_level.connect(self._ide_page.set_mic_level)

        self._metrics_worker = MetricsWorker(parent=self)
        self._metrics_worker.snapshot_ready.connect(self._on_metrics_snapshot)
        if not self._test_mode:
            self._metrics_worker.start()

        root.addWidget(splitter, 1)

        shell = FramelessShell(self)
        shell.set_center_widget(central)
        self.setCentralWidget(shell)
        apply_cyberspace_theme(self)

        self._chat.send_clicked.connect(lambda t: self._on_user_text(t, from_voice=False))

        self._monitor_mgr = MonitorManager(
            self._settings,
            self._db,
            self._gemma,
            self._term_log,
            self._browser,
            notification_policy=self._notif_policy,
            parent=self,
        )
        # YouTube DOM play 경로 — MediaPlaybackFlow가 허용 탭 결과를 읽음
        self._assistant._browser_monitor = self._browser  # noqa: SLF001
        self._monitor_mgr.alert_emitted.connect(self._on_monitor_alert)
        self._monitor_mgr.targets_changed.connect(self._on_targets_changed)

        act_quit = QAction("종료", self)
        act_quit.triggered.connect(self.close)
        self.addAction(act_quit)

        # 기본 크기(리사이즈 가능) — 전체화면은 타이틀바 □ 버튼으로 전환
        self.resize(1280, 800)
        center_on_screen(self)
        # 무거운 백그라운드 서비스는 창 표시 후 — show()·첫 페인트 블로킹 완화
        if not self._test_mode:
            QTimer.singleShot(0, self._deferred_startup_services)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        suppress_native_window_border(self)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._drag.set_maximized(self.isMaximized())
            self._viz.request_sync_orb_anchor("window_state_change")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._viz.request_sync_orb_anchor("main_window_resize")

    def _deferred_startup_services(self) -> None:
        """창이 뜬 뒤 상시 음성·모니터·STT 워밍업 시작."""
        self._check_recoverable_tasks()
        if self._settings.always_listen_enabled:
            self._continuous_listen.start()
            self._notes.add_note("상시 음성 대기: 말씀하시면 인식합니다.")
        self._warmup_stt_async()
        self._monitor_mgr.start()
        self._state.reset_to_idle()
        self._viz.set_state(AppState.IDLE)

    def _check_recoverable_tasks(self) -> None:
        """앱 재시작 시 중단 Task 알림."""
        try:
            from iris.application.runtime_factory import build_task_runtime

            runtime = build_task_runtime(self._db, self._executor.tool_registry)
            recoverable = runtime.recovery.normalize_startup_tasks()
            if not recoverable:
                return
            task = recoverable[0]
            snap = runtime.recovery.load_recovery_snapshot(task.id)
            summary = task.goal[:80]
            if snap and snap.pending_approval:
                summary += " (승인 대기 중)"
            msg = (
                f"이전 작업이 중단되었습니다: {summary}\n"
                "계속하려면 '계속 진행', 상태는 '상태 확인', "
                "취소하려면 '작업 취소'라고 입력해 주세요."
            )
            self._chat.append_assistant(msg)
            self._assistant.ctx.active_task_id = task.id
            health = self._assistant.task_runtime_health
            if health.status == "failed":
                self._chat.append_assistant(
                    f"Task Runtime 경고: {health.error_message or health.error_type}"
                )
        except Exception as exc:
            self._db.insert_log("task_runtime", "recovery_check_failed", str(exc)[:300])

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

    def _init_voice_pipeline(self) -> None:
        """음성 세션·상시 듣기·barge-in 파이프라인 구성."""
        self._voice_session = VoiceSessionController(
            self._settings,
            on_followup_pause=self._voice_gate.pause_followup_timer,
            on_followup_resume=self._voice_gate.resume_followup_timer,
            parent=self,
        )
        self._voice_session.state_changed.connect(self._on_voice_session_state)
        self._voice_session.barge_in_detected.connect(self._bridge.barge_in.emit)
        self._barge = BargeInMonitor(
            self._tts,
            grace_ms=self._settings.barge_in_grace_ms,
        )
        self._continuous_listen = ContinuousListenController(
            self._settings,
            self._stt,
            self._voice_session,
            barge=self._barge,
            parent=self,
        )
        self._continuous_listen.utterance_ready.connect(self._on_voice_utterance)
        self._continuous_listen.listen_failed.connect(self._on_listen_failed)
        self._continuous_listen.speech_started.connect(self._on_speech_started)
        self._continuous_listen.stt_started.connect(self._on_stt_started)
        self._continuous_listen.utterance_rejected.connect(self._on_utterance_rejected)

    def _rebuild_voice_input(self) -> None:
        """마이크 설정 변경 후 음성 입력 컨트롤러를 재구성한다."""
        if hasattr(self, "_continuous_listen"):
            self._continuous_listen.stop()
        self._stt = SttEngine(self._settings)
        self._voice_gate = VoiceCommandGate(
            wake_words=self._settings.voice_wake_words,
            require_wake_word=self._settings.voice_require_wake_word,
            followup_seconds=self._settings.voice_followup_seconds,
        )
        self._voice_stt_reject_streak = 0
        self._init_voice_pipeline()
        self._voice_session.set_barge_in_enabled(self._settings.barge_in_enabled)
        self._continuous_listen.mic_level.connect(self._viz.set_mic_level)
        self._continuous_listen.mic_level.connect(self._chat.set_mic_level)
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
        name = self._settings.gemma_model_name.strip()
        if isinstance(self._status_strip, TopStatusHeader):
            self._status_strip.set_model_name(name)
        else:
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
        self._gemma = GemmaClient(
            self._settings,
            timeout_sec=self._settings.llm_timeout_seconds,
        )
        self._refresh_app_paths()
        self._assistant = IrisAssistant(
            self._db, self._executor, self._gemma, self._app_paths, self._settings
        )
        self._dialogue = DialogueAgent(self._assistant, self._gemma)
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

    def _open_user_profile_dialog(self) -> None:
        dlg = UserProfileDialog(self._db, self)
        dlg.exec()

    def _open_settings_dialog(self) -> None:
        # 설정창 마이크 미리보기와 상시 듣기가 동시에 같은 장치를 잡지 않도록
        resume_listen = self._settings.always_listen_enabled
        self._continuous_listen.stop()
        dlg = SettingsDialog(
            self._settings,
            self,
            db=self._db,
            on_app_paths_changed=self._refresh_app_paths,
            browser_monitor=self._browser,
            extension_server_active=self._monitor_mgr.extension_ingest_server_active,
            ensure_extension_server=self._monitor_mgr.ensure_extension_ingest_server,
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

    @pyqtSlot(object)
    def _on_voice_session_state(self, state: object) -> None:
        if isinstance(state, VoiceSessionState):
            push_activity_line(f"VoiceSession: state {state.value.upper()}.")

    @pyqtSlot()
    def _barge_slot(self) -> None:
        self._voice_session.enter_listening()
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
        result = dispatch_proactive_monitor_event(
            self._assistant,
            self._dialogue,
            title=title,
            message=message,
            category=category,
            target_id=target_id,
            focus_hint=focus_hint,
            recommended=recommended,
            event_id=event_id,
        )
        if result is None:
            return
        if result.show_in_chat:
            self._chat.append_message("Iris", result.proposal)

    def _on_state_changed(self, s: object) -> None:
        if isinstance(s, AppState):
            self._viz.set_state(s)
            self._ide_page.set_app_state(s)
            self._system_sounds.play_state(s, QDateTime.currentMSecsSinceEpoch())
            if isinstance(self._status_strip, TopStatusHeader):
                self._status_strip.set_app_state(s)
                self._status_strip.refresh_backend_status(self._settings)
            else:
                self._status_label.setText(f"상태: {s.name}")
            push_activity_line(f"UI: app state → {s.name}.")

    def _pause_voice_input(self) -> None:
        self._voice_session.on_agent_processing_started()

    def _resume_voice_input(self) -> None:
        if self._state.state not in (
            AppState.PROCESSING,
            AppState.EXECUTING,
            AppState.RESPONDING,
        ):
            self._voice_session.on_agent_processing_finished()

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

    @pyqtSlot(str)
    def _on_utterance_rejected(self, reason: str) -> None:
        """no-speech·저신뢰 — 채팅 오염 없이 조용히 무시 (연속 실패 시만 안내)."""
        self._chat.cancel_user_listening()
        self._state.reset_to_idle()
        self._voice_stt_reject_streak += 1
        if "low_logprob" in reason and self._voice_stt_reject_streak >= 2:
            self._chat.append_message("Iris", "잘 못 들었어요. 다시 말씀해 주세요.")
            self._voice_stt_reject_streak = 0

    @pyqtSlot(str)
    def _on_listen_failed(self, message: str) -> None:
        # 상시 대기 중 인식 실패는 조용히 무시 (텍스트 입력 가능)
        if "음성을 인식하지 못했습니다" in message:
            return
        self._notes.add_note(message)

    @pyqtSlot(str)
    def _on_voice_utterance(self, text: str) -> None:
        push_activity_line("STT: utterance ready (accepted for gating pipeline).")
        self._voice_stt_reject_streak = 0
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
            self._iris_reply("네, 말씀하세요.", spoken="네, 말씀하세요.")
            return
        self._pause_voice_input()
        self._chat.complete_user_message_typed(gated.command_text)
        self._on_user_text(gated.command_text, from_voice=True, already_shown=True)

    @pyqtSlot(object)
    def _on_tts_status_changed(self, _status: object) -> None:
        label = self._tts.status_label
        if isinstance(self._status_strip, TopStatusHeader):
            self._status_strip.set_tts_status(label)
        else:
            self._tts_status_label.setText(label)
        if isinstance(_status, TtsStatus) and _status is TtsStatus.TTS_ERROR:
            notice = getattr(self._tts, "_last_user_notice", None)
            if notice:
                self._notes.add_note(notice)

    def _tts_playback_duration_ms(self, spoken: str) -> float:
        """현재 TTS 재생 길이(ms) — 미측정 시 텍스트로 추정."""
        base_ms = self._tts.current_playback_duration_ms
        if base_ms > 0:
            return float(base_ms)
        return estimate_speech_duration_ms(
            spoken,
            self._settings.tts_speaking_rate,
        )

    def _sync_iris_chat_typing(self, visible: str, spoken: str) -> None:
        """채팅 타이핑 속도를 TTS 재생 길이에 맞춘다."""
        visible_text = visible.strip()
        spoken_text = spoken.strip() or visible_text
        base_ms = self._tts_playback_duration_ms(spoken_text)
        self._chat.sync_typing_to_speech(
            base_ms,
            visible_len=len(visible_text),
            spoken_len=max(len(spoken_text), 1),
        )

    def _iris_reply(
        self,
        visible: str,
        *,
        spoken: str | None = None,
        from_llm: bool = False,
        max_sentences: int | None = None,
        on_complete: object | None = None,
    ) -> None:
        """Iris 답변 — TTS 재생과 동일한 속도로 채팅 타이핑."""
        body = visible.strip()
        if not body:
            return
        if spoken is None:
            tone = infer_speech_tone(from_llm=from_llm, reply_text=body)
            if self._settings.tts_enable_speech_formatter:
                cap = (
                    max_sentences
                    if max_sentences is not None
                    else self._settings.tts_max_spoken_sentences
                )
                spoken_text = format_speech(body, tone, max_sentences=cap)
            else:
                spoken_text = body
        else:
            spoken_text = spoken.strip() or body

        self._chat.append_message_typed("Iris", body, speech_sync=True)
        if self._workspace_mode == "ide":
            self._ide_page.active_chat().append_message_typed("Iris", body, speech_sync=True)
        self._speak(
            spoken_text,
            on_complete=on_complete,
            after_playback_start=lambda: self._sync_iris_chat_typing(body, spoken_text),
        )

    def _speak(
        self,
        text: str,
        *,
        on_complete: object | None = None,
        after_playback_start: Callable[[], None] | None = None,
        flush_typing_on_done: bool = True,
    ) -> None:
        def on_synthesis_start() -> None:
            self._state.set_state(AppState.PROCESSING)
            self._voice_session.on_tts_synthesis_started()

        def on_playback_start() -> None:
            self._state.set_state(AppState.RESPONDING)
            self._voice_session.on_tts_playback_started()
            if self._settings.barge_in_enabled:
                self._barge.notify_tts_started()
            if after_playback_start:
                after_playback_start()

        def on_done() -> None:
            self._chat.on_speech_typing_finished(flush=flush_typing_on_done)
            self._barge.reset()
            self._voice_session.on_tts_playback_finished()
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
        use_coding_panel: bool = False,
    ) -> None:
        text = text.strip()
        chat = (
            self._ide_page.coding_panel.chat
            if use_coding_panel
            else self._active_chat_panel()
        )
        if not text:
            if from_voice:
                chat.cancel_user_listening()
            self._resume_voice_input()
            return
        self._pause_voice_input()
        self._state.set_state(AppState.LISTENING)
        if not already_shown:
            if from_voice:
                chat.complete_user_message_typed(text)
            else:
                chat.append_message_instant("나", text)
        # 진행 중 턴은 memory에 넣지 않음 — 턴 완료 시 user+assistant 한꺼번에 커밋
        self._db.insert_log("user", text, None)
        push_activity_line(
            f"UI: user turn submitted ({'voice' if from_voice else 'text'}), log row written."
        )
        self._state.set_state(AppState.PROCESSING)
        self._voice_session.on_agent_processing_started()
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
        self._agent_worker.delegate_dialogue_stream.connect(
            self._on_delegate_dialogue_stream,
            Qt.ConnectionType.QueuedConnection,
        )
        self._agent_worker.frontier_stream.connect(
            self._on_frontier_stream,
            Qt.ConnectionType.QueuedConnection,
        )
        self._agent_worker.early_ack.connect(
            self._on_agent_early_ack,
            Qt.ConnectionType.QueuedConnection,
        )
        self._agent_worker.user_notify.connect(
            self._on_agent_user_notify,
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
        self._iris_reply(
            ack,
            from_llm=False,
            max_sentences=min(2, self._settings.tts_max_spoken_sentences),
            on_complete=self._on_early_ack_tts_done,
        )

    @pyqtSlot(str)
    def _on_agent_user_notify(self, msg: str) -> None:
        """키보드·단축키·마우스 사용 전 충돌 방지 안내."""
        body = msg.strip()
        if not body:
            return
        self._db.insert_log("assistant_user_notify", body, None)
        self._iris_reply(
            body,
            from_llm=False,
            max_sentences=min(3, self._settings.tts_max_spoken_sentences),
        )

    def _on_early_ack_tts_done(self) -> None:
        """ack TTS 종료 — 워커 실행 중이면 EXECUTING, follow-up 대기."""
        self._early_ack_tts_done = True
        if not self._final_reply_received:
            self._state.set_state(AppState.EXECUTING)
            self._voice_session.on_agent_processing_started()
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

        self._db.insert_log("assistant", user_visible, None)
        self._commit_completed_turn(user_visible, store_history=store_history)

        if spoken_followup.strip():
            self._iris_reply(spoken_followup, from_llm=False)
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

    @pyqtSlot(str, str, str, str)
    def _on_agent_delegate_search(
        self,
        text: str,
        intent_name: str,
        slot_query: str = "",
        search_meta_json: str = "",
    ) -> None:
        try:
            intent = CommandKind[intent_name]
        except KeyError:
            intent = CommandKind.WEB_SEARCH
        sq = slot_query.strip() or None
        meta = self._parse_search_meta(search_meta_json)
        self._start_search_worker(
            text,
            intent,
            slot_query=sq,
            slot_queries=meta.get("queries") or None,
            search_meta_json=search_meta_json,
        )

    @staticmethod
    def _parse_search_meta(raw: str) -> dict:
        if not raw or not raw.strip():
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _start_search_worker(
        self,
        text: str,
        intent: CommandKind,
        *,
        slot_query: str | None = None,
        slot_queries: list[str] | None = None,
        search_meta_json: str = "",
    ) -> None:
        self._search_worker = SearchWorker(
            text,
            intent=intent,
            slot_query=slot_query,
            slot_queries=slot_queries,
            search_meta_json=search_meta_json,
        )
        self._search_worker.finished_hits.connect(self._on_search_done)
        self._search_worker.start()

    def _on_search_done(
        self,
        query: str,
        hits: object,
        intent_name: str,
        search_meta_json: str = "",
    ) -> None:
        push_activity_line(
            f"UI: search worker returned intent={intent_name!r} hit_count={len(hits)}."
        )
        try:
            intent = CommandKind[intent_name]
        except KeyError:
            intent = CommandKind.WEB_SEARCH
        meta = self._parse_search_meta(search_meta_json)
        hybrid = bool(meta.get("hybrid"))
        self._db.insert_log("web", query, f"hits={len(hits)} intent={intent.name}")  # type: ignore[arg-type]
        hit_list = list(hits)  # type: ignore[arg-type]
        quality = assess_research_quality(hit_list)
        comparison = str(meta.get("answer_shape") or "").strip().lower() == "comparison"
        answer_mode = resolve_answer_mode(
            comparison=comparison,
            hybrid=hybrid,
            quality=quality,
        )
        push_activity_line(
            f"UI: research quality score={quality.score} tier={quality.tier} "
            f"mode={answer_mode}."
        )

        ctx = self._build_search_llm_context(
            query,
            hit_list,
            intent_label=intent.name,
            answer_mode=answer_mode,
            quality=quality,
        )

        messages = self._dialogue.build_messages(
            self._last_user_text,
            history=self._dialogue_history_slice(),
            extra_context=ctx,
        )
        push_activity_line(
            "UI: summarization LlmWorker starting (stream) with search context."
        )
        self._start_streaming_llm_worker(
            messages,
            store_history=True,
            add_iris_prefix=False,
        )

    def _build_search_llm_context(
        self,
        query: str,
        hit_list: list,
        *,
        intent_label: str,
        answer_mode: str,
        quality: ResearchQuality,
    ) -> str:
        """P1/P3/P4 — 검색 실패·부분 성공도 LLM 프롬프트로 degrade (즉시 failure UI 금지)."""
        reason = quality.reason_ko or ""
        if answer_mode == "search_degraded":
            push_activity_line(f"UI: P1 search degraded — {reason!r}.")
            return format_search_degraded_context(
                query, intent_label=intent_label, reason=reason
            )
        if answer_mode == "comparison_degraded":
            push_activity_line(f"UI: P3 comparison degraded — {reason!r}.")
            return format_comparison_degraded_context(
                query, intent_label=intent_label, reason=reason
            )
        if answer_mode == "hybrid_empty":
            push_activity_line(f"UI: hybrid empty — {reason!r}.")
            return format_hybrid_without_hits(
                query, intent_label=intent_label, reason=reason
            )
        return format_hits_for_gemma_context(
            query,
            hit_list,
            intent_label=intent_label,
            answer_mode=answer_mode,  # type: ignore[arg-type]
            quality=quality,
        )

    def _dialogue_history_slice(self) -> list[ChatMessage]:
        turns = self._settings.dialogue_history_turns
        if turns <= 0:
            return []
        return self._history[-(turns * 2) :]

    def _reset_stream_state(self, *, store_history: bool, add_iris_prefix: bool) -> None:
        self._stream_buffer = ""
        self._stream_tts_first_done = False
        self._stream_tts_spoken_len = 0
        self._stream_store_history = store_history
        self._stream_reply_ready = False
        self._stream_add_iris_prefix = add_iris_prefix
        self._stream_final_visible = ""

    def _start_streaming_llm_worker(
        self,
        messages: list[ChatMessage],
        *,
        store_history: bool,
        add_iris_prefix: bool,
    ) -> None:
        self._reset_stream_state(
            store_history=store_history,
            add_iris_prefix=add_iris_prefix,
        )
        self._chat.begin_stream_message("Iris")
        if self._llm_worker and self._llm_worker.isRunning():
            self._llm_worker.requestInterruption()
        self._llm_worker = LlmWorker(
            self._assistant.gemma_client,
            messages,
            stream=True,
        )
        self._llm_worker.chunk_received.connect(self._on_llm_stream_chunk)
        self._llm_worker.finished_text.connect(self._on_llm_stream_finished)
        self._llm_worker.start()

    @pyqtSlot(str)
    def _on_delegate_dialogue_stream(self, user_text: str) -> None:
        messages = self._dialogue.build_messages(
            user_text,
            history=self._dialogue_history_slice(),
        )
        push_activity_line("UI: streaming dialogue LlmWorker starting.")
        self._start_streaming_llm_worker(
            messages,
            store_history=True,
            add_iris_prefix=True,
        )

    @pyqtSlot(str, bool)
    def _on_frontier_stream(self, reply: str, store_history: bool) -> None:
        """Frontier 선행 말 — 이미 수신한 문자열을 채팅·TTS 스트리밍 재생."""
        body = (reply or "").strip()
        if not body:
            if store_history:
                self._state.reset_to_idle()
                self._resume_voice_input()
            return
        if not store_history:
            self._early_ack_tts_done = False
            self._final_reply_received = False
            self._skip_followup_tts = False
            self._db.insert_log("assistant_frontier", body, None)
        push_activity_line(
            f"UI: frontier prefetched stream store_history={store_history}."
        )
        self._play_prefetched_stream(
            body,
            store_history=store_history,
            add_iris_prefix=True,
        )

    def _play_prefetched_stream(
        self,
        text: str,
        *,
        store_history: bool,
        add_iris_prefix: bool,
    ) -> None:
        """LLM 2회 없이 수신 완료된 본문을 chunk 단위로 UI 재생."""
        self._reset_stream_state(
            store_history=store_history,
            add_iris_prefix=add_iris_prefix,
        )
        self._chat.begin_stream_message("Iris")
        body = text.strip()
        step = max(1, len(body) // 24)
        for i in range(0, len(body), step):
            self._on_llm_stream_chunk(body[i : i + step])
        visible = body
        if add_iris_prefix:
            from iris.assistant.dialogue_agent import DialogueAgent

            visible = DialogueAgent._with_iris_prefix(body)
        self._on_llm_stream_finished(visible)

    @pyqtSlot(str)
    def _on_llm_stream_chunk(self, chunk: str) -> None:
        self._chat.append_stream_chunk(chunk)
        self._stream_buffer += chunk
        if self._stream_tts_first_done:
            return
        end = find_first_sentence_end(self._stream_buffer)
        if end is None:
            return
        first = self._stream_buffer[:end].strip()
        if not first:
            return
        self._stream_tts_first_done = True
        self._stream_tts_spoken_len = end
        tone = infer_speech_tone(from_llm=True, reply_text=first)
        if self._settings.tts_enable_speech_formatter:
            spoken = format_speech(first, tone, max_sentences=1)
        else:
            spoken = first

        def _on_first_tts_done() -> None:
            if self._stream_reply_ready:
                self._speak_stream_remainder()

        self._speak(
            spoken,
            on_complete=_on_first_tts_done,
            after_playback_start=lambda s=spoken: self._sync_iris_chat_typing(
                self._chat.typing_buffer_text,
                s,
            ),
            flush_typing_on_done=False,
        )

    @pyqtSlot(str)
    def _on_llm_stream_finished(self, text: str) -> None:
        visible = text.strip()
        if self._stream_add_iris_prefix:
            visible = DialogueAgent._with_iris_prefix(visible)
        self._stream_final_visible = visible
        self._stream_reply_ready = True
        self._chat.end_stream_message(visible)
        self._db.insert_log("assistant", visible, None)
        self._commit_completed_turn(visible, store_history=self._stream_store_history)
        if self._stream_tts_first_done:
            if not self._tts.is_speaking():
                self._speak_stream_remainder()
        else:
            self._speak_stream_full(visible)

    def _speak_stream_full(self, visible: str) -> None:
        tone = infer_speech_tone(
            from_llm=self._stream_store_history,
            reply_text=visible,
        )
        if self._settings.tts_enable_speech_formatter:
            spoken = format_speech(
                visible,
                tone,
                max_sentences=self._settings.tts_max_spoken_sentences,
            )
        else:
            spoken = visible
        visible_body = strip_iris_prefix(visible)
        self._speak(
            spoken,
            after_playback_start=lambda: self._sync_iris_chat_typing(
                visible_body,
                spoken,
            ),
            flush_typing_on_done=True,
        )

    def _speak_stream_remainder(self) -> None:
        full = self._stream_final_visible
        body = strip_iris_prefix(full)
        remainder = body[self._stream_tts_spoken_len :].strip()
        if not remainder:
            self._bridge.tts_finished.emit()
            self._resume_voice_input()
            return
        tone = infer_speech_tone(
            from_llm=self._stream_store_history,
            reply_text=full,
        )
        max_sent = max(1, self._settings.tts_max_spoken_sentences - 1)
        if self._settings.tts_enable_speech_formatter:
            spoken = format_speech(remainder, tone, max_sentences=max_sent)
        else:
            spoken = remainder
        self._speak(
            spoken,
            after_playback_start=lambda s=spoken: self._chat.extend_typing_for_speech_segment(
                s,
                self._tts_playback_duration_ms(s),
            ),
            flush_typing_on_done=True,
        )

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
        self._db.insert_log("assistant", text, None)
        self._commit_completed_turn(text, store_history=store_history)
        self._iris_reply(text, from_llm=store_history)

    def current_workspace(self) -> str:
        return self._workspace_mode

    def _ensure_status_in_title_bar(self) -> None:
        """STATE/MODEL/TTS + 백엔드 — 모든 workspace에서 타이틀 바 2행 고정."""
        self._drag.place_status_rows(
            self._status_header.status_widget(),
            self._status_header.backend_row(),
        )

    def _apply_ui_overlay_margins(self, mode: str) -> None:
        """IDE는 Theia Activity Bar가 창 좌우 끝에 맞닿도록 가로 여백 제거."""
        vertical = TOKENS.spacing_sm
        if mode == "ide":
            self._ui_root_lay.setContentsMargins(0, vertical, 0, vertical)
        else:
            self._ui_root_lay.setContentsMargins(
                TOKENS.spacing_lg,
                vertical,
                TOKENS.spacing_lg,
                vertical,
            )

    def switch_to_assistant_workspace(self) -> None:
        if self._workspace_mode == "assistant":
            return
        if self._workspace_mode == "ide":
            self._ide_splitter_state = self._ide_page.save_splitter_state()
        self._workspace_stack.setCurrentWidget(self._assistant_page)
        self._workspace_mode = "assistant"
        self._ensure_status_in_title_bar()
        self._viz.setVisible(True)
        self._viz.set_orb_anchor(self._orb_spacer)
        self._left_sidebar.utility.actions.update_action(
            "ide",
            tooltip="Iris IDE 작업공간으로 전환",
        )
        self._left_sidebar.utility.actions.set_action_active("ide", False)
        self._left_sidebar.utility.actions.set_action_active("email", False)
        self._left_sidebar.utility.actions.set_action_visible("ide", True)
        self._left_sidebar.set_workspace_mode("assistant")
        self._apply_ui_overlay_margins("assistant")
        total = max(sum(self._workspace_splitter.sizes()), self.width())
        self._workspace_splitter.setSizes([self._sidebar_split_size, max(0, total - self._sidebar_split_size)])
        self._viz.request_sync_orb_anchor("switch_to_assistant")
        self._assistant_page.restore_splitter_state(self._assistant_splitter_state)
        self._metrics_worker.set_active(True)

    def switch_to_ide_workspace(self) -> None:
        if self._workspace_mode == "ide":
            return
        if self._workspace_mode == "assistant":
            self._assistant_splitter_state = self._assistant_page.save_splitter_state()
        self._workspace_stack.setCurrentWidget(self._ide_page)
        self._workspace_mode = "ide"
        self._ensure_status_in_title_bar()
        self._viz.setVisible(False)
        self._viz.set_orb_anchor(None)
        sizes = self._workspace_splitter.sizes()
        if sizes and sizes[0] > 0:
            self._sidebar_split_size = sizes[0]
        total = max(sum(sizes), self.width())
        self._workspace_splitter.setSizes([0, total])
        self._left_sidebar.set_workspace_mode("ide")
        self._left_sidebar.utility.actions.set_action_active("email", False)
        self._apply_ui_overlay_margins("ide")
        self._ide_page.restore_splitter_state(self._ide_splitter_state)
        self._ide_page.show_empty_home()
        ctx = self._ide_bridge.get_context()
        summary = ctx.summary_line()
        self._ide_page.set_workspace_label(summary)
        self._metrics_worker.set_active(True)

    def switch_to_email_workspace(self) -> None:
        if self._workspace_mode == "email":
            return
        if self._workspace_mode == "assistant":
            self._assistant_splitter_state = self._assistant_page.save_splitter_state()
        elif self._workspace_mode == "ide":
            self._ide_splitter_state = self._ide_page.save_splitter_state()
        self._workspace_stack.setCurrentWidget(self._email_page)
        self._workspace_mode = "email"
        self._ensure_status_in_title_bar()
        self._viz.setVisible(False)
        self._viz.set_orb_anchor(None)
        self._left_sidebar.set_workspace_mode("assistant")
        self._left_sidebar.utility.actions.set_action_active("ide", False)
        self._left_sidebar.utility.actions.set_action_active("email", True)
        self._apply_ui_overlay_margins("assistant")
        total = max(sum(self._workspace_splitter.sizes()), self.width())
        self._workspace_splitter.setSizes([self._sidebar_split_size, max(0, total - self._sidebar_split_size)])
        self._email_page.refresh()
        self._metrics_worker.set_active(True)

    def _on_ide_toggle(self) -> None:
        if self._workspace_mode == "ide":
            self.switch_to_assistant_workspace()
            return
        # 백엔드 준비/오류 UI를 보여주려면 성공 여부와 관계없이 IDE 페이지로 먼저 전환
        self.switch_to_ide_workspace()
        self._ensure_ide_visible()

    def _ensure_ide_visible(self) -> None:
        """IDE 진입 — READY면 즉시 WebView 복원, 아니면 Backend+Frontend 로드."""
        if self._ide_page.theia.resume_or_continue():
            if self._ide_page.theia.state == TheiaViewState.READY:
                self._on_theia_ready()
            return
        self._start_ide_backend_and_load()

    def _start_ide_backend_and_load(self, *, force_reload: bool = False) -> None:
        # 재시도(force)만 전체 초기화 — 일반 재진입은 READY WebView 유지
        if force_reload or self._ide_page.theia.state == TheiaViewState.ERROR:
            self._ide_page.theia.reset_view(force=True)
        elif self._ide_page.theia.resume_or_continue():
            if self._ide_page.theia.state == TheiaViewState.READY:
                self._on_theia_ready()
            return
        self._ide_page.theia.set_preflight("Iris IDE 환경을 확인하는 중…")
        try:
            workspace = resolve_ide_workspace(self._settings)
        except (FileNotFoundError, NotADirectoryError) as exc:
            self._ide_page.theia.set_error(str(exc), failure_kind="BackendFailure")
            return

        preflight_log = Path.home() / ".iris" / "logs" / "ide-preflight.log"
        report = run_ide_preflight(workspace, log_path=preflight_log)
        if not report.ready:
            self._ide_page.theia.set_error(
                format_preflight_error(report),
                log_path=str(preflight_log),
                failure_kind="BackendFailure",
            )
            return

        self._ide_page.theia.set_starting("Theia Backend를 시작하는 중…")

        # 이미 동일 workspace Backend가 살아 있으면 Worker 없이 Frontend만 재로드
        if self._ide_backend.is_running:
            status = BackendStatus(
                True,
                self._ide_backend.frontend_url,
                port=0,
                log_path=str(Path.home() / ".iris" / "logs" / "ide-backend.log"),
            )
            self._on_ide_backend_ready(status)
            return

        self._stop_ide_backend_worker()
        thread = QThread(self)
        worker = IdeBackendWorker(self._ide_backend)
        worker.moveToThread(thread)
        thread.started.connect(lambda: worker.start_backend(workspace))
        worker.backend_ready.connect(self._on_ide_backend_ready)
        worker.backend_failed.connect(self._on_ide_backend_failed)
        worker.backend_ready.connect(thread.quit)
        worker.backend_failed.connect(thread.quit)
        worker.backend_ready.connect(worker.deleteLater)
        worker.backend_failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._ide_backend_thread = thread
        self._ide_backend_worker = worker
        thread.start()

    def _stop_ide_backend_worker(self) -> None:
        if self._ide_backend_thread is not None and self._ide_backend_thread.isRunning():
            self._ide_backend_thread.quit()
            self._ide_backend_thread.wait(3000)
        self._ide_backend_thread = None
        self._ide_backend_worker = None

    @pyqtSlot(object)
    def _on_ide_backend_ready(self, status: object) -> None:
        if not isinstance(status, BackendStatus) or not status.running:
            return
        bridge_url = self._ide_bridge.base_url
        url = f"{status.frontend_url}?irisBridgePort={self._ide_bridge.port}"
        if self._ide_page.theia.load_url(url):
            self._pending_bridge_url = bridge_url

    @pyqtSlot(object)
    def _on_ide_backend_failed(self, status: object) -> None:
        if isinstance(status, BackendStatus):
            self._ide_page.theia.set_error(
                status.error,
                log_path=status.log_path,
                failure_kind="BackendFailure",
            )

    def _on_theia_ready(self) -> None:
        bridge_url = getattr(self, "_pending_bridge_url", "")
        if bridge_url:
            self._ide_page.theia.run_javascript(
                f"window.__IRIS_BRIDGE_URL__ = {json.dumps(bridge_url)};"
            )

    def _run_ide_diagnose(self) -> None:
        root = _find_repo_root()
        script = root / "scripts" / "diagnose-iris-ide.ps1"
        if script.is_file():
            subprocess_run = __import__("subprocess").run
            subprocess_run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                shell=False,
            )
        else:
            py = root / "iris" / "scripts" / "diagnose_webengine.py"
            if py.is_file():
                __import__("subprocess").run([sys.executable, str(py)], shell=False)

    def _run_ide_env_recovery(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "IDE 환경 복구",
            "Iris 가상환경에 PyQt6-WebEngine(6.11.0)을 설치합니다.\n"
            "Theia 빌드는 포함하지 않습니다.\n\n계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = recover_webengine(install_theia=False)
        self._chat.append_message_instant(
            "Iris",
            f"{result.message}\n로그: {result.log_path}",
        )
        if result.success:
            self._start_ide_backend_and_load()

    def _show_ide_log(self) -> None:
        logs_dir = Path.home() / ".iris" / "logs"
        preflight = (logs_dir / "ide-preflight.log").read_text(encoding="utf-8", errors="replace") if (logs_dir / "ide-preflight.log").is_file() else ""
        backend_tail = tail_backend_log(max_lines=120)
        web_tail = tail_webengine_log(max_lines=120)
        path = self._ide_page.theia.last_log_path() or str(logs_dir / "ide-backend.log")
        body = (
            f"=== ide-preflight.log ===\n{preflight[-2000:]}\n\n"
            f"=== ide-backend.log (tail) ===\n{backend_tail}\n\n"
            f"=== ide-webengine.log (tail) ===\n{web_tail}\n\n"
            f"전체 경로: {path}"
        )
        self._chat.append_message_instant("Iris", body[:6000])

    @pyqtSlot(object)
    def _on_metrics_snapshot(self, snap: object) -> None:
        from iris.system.metrics_snapshot import MetricsSnapshot

        if isinstance(snap, MetricsSnapshot):
            self._left_sidebar.utility.metrics.apply_snapshot(snap)

    @pyqtSlot(bool, str, str, str)
    def _on_ide_editor_state_changed(
        self,
        has_open_editor: bool,
        title: str,
        _uri: str,
        language_id: str,
    ) -> None:
        if self._workspace_mode != "ide":
            return
        self._ide_page.set_editor_state(
            has_open_editor,
            title=title,
            language_id=language_id,
        )

    def _on_coding_user_text(self, text: str) -> None:
        ctx_block = self._ide_bridge.build_message_context_block()
        if ctx_block:
            text = f"{text}\n\n{ctx_block}"
        self._on_user_text(text, from_voice=False, use_coding_panel=True)

    def _active_chat_panel(self):
        if self._workspace_mode == "ide":
            return self._ide_page.active_chat()
        return self._chat

    def closeEvent(self, event: QCloseEvent) -> None:
        register_activity_sink(None)
        self._metrics_worker.set_active(False)
        self._metrics_worker.request_stop()
        self._metrics_worker.wait(2000)
        self._ide_bridge.stop()
        self._stop_ide_backend_worker()
        self._ide_backend.shutdown()
        self._monitor_mgr.stop()
        self._continuous_listen.stop()
        self._tts.stop()
        self._barge.reset()
        self._db.close()
        event.accept()
