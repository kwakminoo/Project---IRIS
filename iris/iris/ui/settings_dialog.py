"""Iris 설정 창."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pathlib import Path

from iris.audio.input_device import (
    MicrophoneScanResult,
    resolve_input_device,
    scan_available_input_devices,
)
from iris.audio.mic_preview import MicLevelPreview
from iris.audio.xtts_engine import is_xtts_installed, resolve_reference_wav
from iris.automation.web_browser import list_installed_browser_options, normalize_browser_key
from iris.config.app_index import build_merged_app_paths
from iris.ai.thinking_policy import normalize_thinking_mode
from iris.config.settings import Settings
from iris.storage.database import Database
from iris.monitoring.browser_tab_monitor import BrowserTabMonitor
from iris.ui.app_launcher_panel import AppLauncherPanel
from iris.ui.integrations_panel import IntegrationsPanel
from iris.ui.chrome_extension_panel import ChromeExtensionPanel
from iris.ui.mic_level_gauge import MicLevelGaugeWidget

_APP_ROOT = Path(__file__).resolve().parent.parent.parent

_COMBO_STYLE = """
QComboBox {
    background-color: #1a1c24;
    color: #ffffff;
    border: 1px solid #3f3f5f;
    border-radius: 4px;
    padding: 4px;
}
"""


@dataclass(frozen=True)
class IrisSettingsSelection:
    model_name: str
    model_names: tuple[str, ...]
    input_device: int | None
    speech_rms: float
    default_web_browser: str
    thinking_mode: str  # off | default | on


class SettingsDialog(QDialog):
    """AI 모델과 입력 마이크를 선택하는 설정 창."""

    def __init__(
        self,
        settings: Settings,
        parent=None,
        *,
        db: Database | None = None,
        on_app_paths_changed: Callable[[], None] | None = None,
        browser_monitor: Optional[BrowserTabMonitor] = None,
        extension_server_active: Callable[[], bool] | None = None,
        ensure_extension_server: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iris 설정")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setMinimumWidth(560)
        self.setMinimumHeight(640)
        self._settings = settings
        self._db = db
        self._on_app_paths_changed = on_app_paths_changed
        self._browser_monitor = browser_monitor
        self._extension_server_active = extension_server_active or (lambda: False)
        self._ensure_extension_server = ensure_extension_server or (lambda: False)
        self._chrome_ext_panel: ChromeExtensionPanel | None = None
        self._models = self._initial_models(settings)
        self._scan_result: MicrophoneScanResult | None = None
        self._app_paths = build_merged_app_paths(db)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.setStyleSheet(
            """
            QDialog, QWidget {
                font-family: "Noto Sans KR", "Segoe UI Variable", "Segoe UI", "Malgun Gothic";
                font-size: 13px;
            }
            """
        )

        title = QLabel("설정")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: #0b1220;
                width: 14px;
                margin: 2px;
                border-radius: 7px;
            }
            QScrollBar:horizontal {
                background: #0b1220;
                height: 14px;
                margin: 2px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical,
            QScrollBar::handle:horizontal {
                background: #334155;
                border: 1px solid #475569;
                border-radius: 7px;
                min-height: 36px;
                min-width: 36px;
            }
            QScrollBar::handle:vertical:hover,
            QScrollBar::handle:horizontal:hover {
                background: #3b82f6;
                border-color: #60a5fa;
            }
            QScrollBar::add-line,
            QScrollBar::sub-line,
            QScrollBar::add-page,
            QScrollBar::sub-page {
                background: transparent;
                border: none;
                width: 0px;
                height: 0px;
            }
            """
        )
        content = QWidget()
        content.setMinimumWidth(760)
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._model_combo = QComboBox()
        self._refresh_model_combo(settings.gemma_model_name)
        form.addRow("사용할 AI 모델", self._model_combo)
        self._model_combo.setStyleSheet(_COMBO_STYLE)

        model_tools = QHBoxLayout()
        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("예: gemma4:e2b, llama3.1:8b")
        btn_add = QPushButton("추가")
        btn_del = QPushButton("삭제")
        btn_add.clicked.connect(self._add_model)
        btn_del.clicked.connect(self._delete_model)
        model_tools.addWidget(self._model_input, 1)
        model_tools.addWidget(btn_add)
        model_tools.addWidget(btn_del)
        form.addRow("모델 관리", model_tools)

        self._browser_combo = QComboBox()
        self._populate_web_browsers(settings.default_web_browser)
        form.addRow("웹 기본 브라우저", self._browser_combo)
        self._browser_combo.setStyleSheet(_COMBO_STYLE)

        if self._browser_monitor is not None:
            self._chrome_ext_panel = ChromeExtensionPanel(
                settings,
                self._browser_monitor,
                server_active=self._extension_server_active,
                ensure_server=self._ensure_extension_server,
                parent=self,
            )
            form.addRow("Chrome 확장", self._chrome_ext_panel)

        self._thinking_combo = QComboBox()
        self._populate_thinking_mode(settings.thinking_mode)
        form.addRow("LLM 추론 (Thinking)", self._thinking_combo)
        self._thinking_combo.setStyleSheet(_COMBO_STYLE)

        self._mic_combo = QComboBox()
        form.addRow("입력 마이크", self._mic_combo)
        self._mic_combo.setStyleSheet(_COMBO_STYLE)

        self._mic_gauge = MicLevelGaugeWidget()
        self._mic_gauge.set_threshold_rms(settings.always_listen_speech_rms)
        form.addRow("마이크 감도", self._mic_gauge)
        self._mic_gauge_help = QLabel(
            "노란 막대를 드래그해 감도를 조절하세요. 막대보다 작은 소리는 인식하지 않습니다."
        )
        self._mic_gauge_help.setWordWrap(True)
        form.addRow("", self._mic_gauge_help)

        self._mic_preview = MicLevelPreview(settings.always_listen_sample_rate, self)
        self._mic_preview.level.connect(self._mic_gauge.set_level)
        self._mic_preview.failed.connect(self._on_mic_preview_failed)
        self._mic_combo.currentIndexChanged.connect(self._restart_mic_preview)

        self._tts_info = QLabel(self._tts_summary_text())
        self._tts_info.setWordWrap(True)
        form.addRow("음성(TTS)", self._tts_info)

        content_lay.addLayout(form)

        if self._db is not None:
            self._integrations = IntegrationsPanel(self._db, parent=self)
            content_lay.addWidget(self._integrations)
            self._app_launcher = AppLauncherPanel(
                self._db,
                on_paths_changed=self._notify_app_paths_changed,
                parent=self,
            )
            content_lay.addWidget(self._app_launcher)

        self._device_help = QLabel("")
        self._device_help.setWordWrap(True)
        content_lay.addWidget(self._device_help)
        self._rescan_microphones(settings.always_listen_input_device)

        self._model_list = QListWidget()
        self._model_list.setMaximumHeight(100)
        self._refresh_model_list()
        content_lay.addWidget(self._model_list)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # 창을 열 때마다 장치 재스캔 — USB 연결·Windows 기본 입력 변경 반영
        self._rescan_microphones(self._selected_input_device())
        self._restart_mic_preview()
        if self._chrome_ext_panel is not None:
            self._chrome_ext_panel.start_polling()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._chrome_ext_panel is not None:
            self._chrome_ext_panel.stop_polling()
        # 시그널·스트림을 먼저 끊어 닫힌 뒤 sounddevice 콜백이 emit 하지 않게 함
        try:
            self._mic_preview.level.disconnect(self._mic_gauge.set_level)
        except (TypeError, RuntimeError):
            pass
        try:
            self._mic_preview.failed.disconnect(self._on_mic_preview_failed)
        except (TypeError, RuntimeError):
            pass
        self._mic_preview.stop()
        super().closeEvent(event)

    def selection(self) -> IrisSettingsSelection:
        model = self._model_combo.currentText().strip() or self._settings.gemma_model_name
        device_data = self._mic_combo.currentData()
        device = int(device_data) if device_data is not None else None
        models = tuple(dict.fromkeys([*self._models, model]))
        browser_data = self._browser_combo.currentData()
        browser = normalize_browser_key(
            str(browser_data) if browser_data is not None else self._settings.default_web_browser
        )
        think_data = self._thinking_combo.currentData()
        thinking_mode = normalize_thinking_mode(
            str(think_data) if think_data is not None else self._settings.thinking_mode
        )
        return IrisSettingsSelection(
            model_name=model,
            model_names=models,
            input_device=device,
            speech_rms=self._mic_gauge.threshold_rms(),
            default_web_browser=browser,
            thinking_mode=thinking_mode,
        )

    def _initial_models(self, settings: Settings) -> list[str]:
        models = list(settings.ai_model_names)
        if settings.gemma_model_name not in models:
            models.insert(0, settings.gemma_model_name)
        return list(dict.fromkeys(m.strip() for m in models if m.strip()))

    def _refresh_model_combo(self, selected: str) -> None:
        self._model_combo.clear()
        self._model_combo.addItems(self._models)
        idx = self._model_combo.findText(selected)
        self._model_combo.setCurrentIndex(max(0, idx))

    def _refresh_model_list(self) -> None:
        self._model_list.clear()
        for model in self._models:
            self._model_list.addItem(model)

    def _add_model(self) -> None:
        model = self._model_input.text().strip()
        if not model or model in self._models:
            return
        self._models.append(model)
        self._model_input.clear()
        self._refresh_model_combo(model)
        self._refresh_model_list()

    def _delete_model(self) -> None:
        model = self._model_combo.currentText().strip()
        if len(self._models) <= 1 or not model:
            return
        self._models = [m for m in self._models if m != model]
        selected = self._models[0]
        self._refresh_model_combo(selected)
        self._refresh_model_list()

    def _populate_thinking_mode(self, selected: str) -> None:
        """Ollama think 전역 정책 — off / default / on."""
        self._thinking_combo.clear()
        options = (
            ("off", "사용 안 함 (All Off)"),
            ("default", "기본 (필요한 실행만)"),
            ("on", "항상 사용 (All On)"),
        )
        for key, label in options:
            self._thinking_combo.addItem(label, key)
        key = normalize_thinking_mode(selected)
        idx = self._thinking_combo.findData(key)
        self._thinking_combo.setCurrentIndex(max(0, idx))

    def _populate_web_browsers(self, selected: str) -> None:
        self._browser_combo.clear()
        options = list_installed_browser_options(self._app_paths)
        selected_key = normalize_browser_key(selected)
        for key, label in options:
            self._browser_combo.addItem(label, key)
        idx = self._browser_combo.findData(selected_key)
        if idx < 0 and options:
            # 저장값이 미설치 브라우저면 첫 항목(보통 Chrome)
            idx = 0
        self._browser_combo.setCurrentIndex(max(0, idx))

    def _rescan_microphones(self, preferred_device: int | None) -> None:
        """마이크 목록 재스캔 — 프로브 통과 장치만 콤보에 표시."""
        try:
            import sounddevice as sd
        except Exception:
            self._scan_result = MicrophoneScanResult(
                None,
                None,
                (),
                "sounddevice 미설치",
            )
            self._populate_microphones(preferred_device)
            self._device_help.setText(self._microphone_help_text())
            return

        self._scan_result = scan_available_input_devices(
            sd,
            sample_rate=self._settings.always_listen_sample_rate,
        )
        self._populate_microphones(preferred_device)
        self._device_help.setText(self._microphone_help_text())

    def _populate_microphones(self, selected_device: int | None) -> None:
        result = self._scan_result
        self._mic_combo.blockSignals(True)
        try:
            self._mic_combo.clear()
            if result is None or not result.devices:
                label = "사용 가능한 마이크 없음"
                if result and result.scan_error:
                    label = f"{label} — {result.scan_error}"
                self._mic_combo.addItem(label, None)
                self._mic_combo.setEnabled(False)
                return

            self._mic_combo.setEnabled(True)
            default_open = any(
                dev.index == result.default_index for dev in result.devices
            )
            if result.default_name:
                default_label = f"Windows 기본 — {result.default_name}"
                if result.default_index is not None:
                    default_label += f" (장치 {result.default_index})"
                if not default_open:
                    default_label += " · 열기 실패"
            else:
                default_label = "Windows 기본 입력 장치"
            self._mic_combo.addItem(default_label, None)

            for dev in result.devices:
                prefix = "★ " if dev.is_system_default else ""
                self._mic_combo.addItem(
                    f"{prefix}{dev.name}  (장치 {dev.index})",
                    dev.index,
                )

            if selected_device is not None:
                idx = self._mic_combo.findData(selected_device)
                if idx >= 0:
                    self._mic_combo.setCurrentIndex(idx)
                    return
            self._mic_combo.setCurrentIndex(0)
        finally:
            self._mic_combo.blockSignals(False)

    def _tts_summary_text(self) -> str:
        s = self._settings
        ref = resolve_reference_wav(s, _APP_ROOT)
        ref_status = ref.name if ref else "없음 (fallback 사용)"
        xtts_pkg = "설치됨" if is_xtts_installed() else "미설치 (requirements-tts.txt)"
        return (
            f"제공자: {s.tts_provider} · 폴백: {s.tts_fallback_provider}\n"
            f"프리셋: {s.tts_voice_preset} · 참조 음성: {ref_status}\n"
            f"XTTS 패키지: {xtts_pkg}\n"
            ".env에서 TTS_PROVIDER, XTTS_REFERENCE_WAV 등을 변경할 수 있습니다."
        )

    def _selected_input_device(self) -> int | None:
        device_data = self._mic_combo.currentData()
        return int(device_data) if device_data is not None else None

    @pyqtSlot()
    def _restart_mic_preview(self) -> None:
        if not self.isVisible():
            return
        self._mic_preview.stop()
        if not self._mic_combo.isEnabled():
            return
        self._mic_preview.start(self._selected_input_device())

    @pyqtSlot(str)
    def _on_mic_preview_failed(self, message: str) -> None:
        self._mic_gauge_help.setText(f"마이크 미리보기 불가: {message}")

    def _notify_app_paths_changed(self) -> None:
        self._app_paths = build_merged_app_paths(self._db)
        if self._on_app_paths_changed:
            self._on_app_paths_changed()

    def _microphone_help_text(self) -> str:
        result = self._scan_result
        if result is None:
            return "마이크 목록을 아직 스캔하지 못했습니다."
        if result.scan_error and not result.devices:
            return f"마이크 스캔 실패: {result.scan_error}"

        lines = [f"스캔 결과: 녹음 가능 {len(result.devices)}개"]
        if result.default_name:
            idx = result.default_index
            suffix = f" (장치 {idx})" if idx is not None else ""
            lines.append(f"Windows 기본 입력: {result.default_name}{suffix}")

        selected = self._selected_input_device()
        if selected is None:
            lines.append("Iris 선택: Windows 기본 입력을 따릅니다.")
        else:
            name = next(
                (dev.name for dev in result.devices if dev.index == selected),
                None,
            )
            if name:
                lines.append(f"Iris 선택: {name} (장치 {selected})")
            else:
                lines.append(f"Iris 선택: 장치 {selected}")

        try:
            import sounddevice as sd
        except Exception:
            return "\n".join(lines)

        choice, reason = resolve_input_device(sd, selected)
        if choice is None:
            lines.append(f"실행 검증 실패: {reason}")
        else:
            lines.append(f"실행 검증: {choice.name} (장치 {choice.device})")
        return "\n".join(lines)
