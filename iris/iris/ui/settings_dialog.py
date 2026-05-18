"""Iris 설정 창."""

from __future__ import annotations

from dataclasses import dataclass

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
    QVBoxLayout,
)

from pathlib import Path

from iris.audio.input_device import list_physical_input_devices, resolve_input_device
from iris.audio.mic_preview import MicLevelPreview
from iris.audio.xtts_engine import is_xtts_installed, resolve_reference_wav
from iris.config.settings import Settings
from iris.ui.mic_level_gauge import MicLevelGaugeWidget

_APP_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class MicrophoneOption:
    index: int
    name: str


@dataclass(frozen=True)
class IrisSettingsSelection:
    model_name: str
    model_names: tuple[str, ...]
    input_device: int | None
    speech_rms: float


def list_microphone_options() -> list[MicrophoneOption]:
    """sounddevice가 현재 PC에서 인식한 물리 마이크 후보만 수집한다."""
    try:
        import sounddevice as sd
    except Exception:
        return []

    return [
        MicrophoneOption(index=device.index, name=device.name)
        for device in list_physical_input_devices(sd)
    ]


class SettingsDialog(QDialog):
    """AI 모델과 입력 마이크를 선택하는 설정 창."""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iris 설정")
        self.setMinimumWidth(520)
        self._settings = settings
        self._models = self._initial_models(settings)
        self._microphones = list_microphone_options()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("설정")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._model_combo = QComboBox()
        self._refresh_model_combo(settings.gemma_model_name)
        form.addRow("사용할 AI 모델", self._model_combo)

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

        self._mic_combo = QComboBox()
        self._populate_microphones(settings.always_listen_input_device)
        form.addRow("입력 마이크", self._mic_combo)

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

        root.addLayout(form)

        self._device_help = QLabel(self._microphone_help_text())
        self._device_help.setWordWrap(True)
        root.addWidget(self._device_help)

        self._model_list = QListWidget()
        self._model_list.setMaximumHeight(100)
        self._refresh_model_list()
        root.addWidget(self._model_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._restart_mic_preview()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._mic_preview.stop()
        super().closeEvent(event)

    def selection(self) -> IrisSettingsSelection:
        model = self._model_combo.currentText().strip() or self._settings.gemma_model_name
        device_data = self._mic_combo.currentData()
        device = int(device_data) if device_data is not None else None
        models = tuple(dict.fromkeys([*self._models, model]))
        return IrisSettingsSelection(
            model_name=model,
            model_names=models,
            input_device=device,
            speech_rms=self._mic_gauge.threshold_rms(),
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

    def _populate_microphones(self, selected_device: int | None) -> None:
        self._mic_combo.clear()
        if not self._microphones:
            self._mic_combo.addItem("사용 가능한 물리 마이크 없음", None)
            self._mic_combo.setEnabled(False)
            return
        self._mic_combo.setEnabled(True)
        for opt in self._microphones:
            self._mic_combo.addItem(f"{opt.name}  (장치 {opt.index})", opt.index)
        if selected_device is not None:
            idx = self._mic_combo.findData(selected_device)
            if idx >= 0:
                self._mic_combo.setCurrentIndex(idx)

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

    def _microphone_help_text(self) -> str:
        try:
            import sounddevice as sd
        except Exception:
            return "sounddevice를 사용할 수 없어 마이크 목록을 불러오지 못했습니다."
        choice, reason = resolve_input_device(sd, self._settings.always_listen_input_device)
        if choice is None:
            return f"현재 선택된 마이크 확인 실패: {reason}"
        return f"현재 입력 장치: {choice.name} (장치 {choice.device})"
