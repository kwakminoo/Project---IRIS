"""설정 창 — Iris Wiki 탭."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from iris.config.settings import Settings
from iris.infrastructure.knowledge.vault_repository import default_vault_path


@dataclass(frozen=True)
class IrisWikiSettingsSelection:
    enabled: bool
    vault_path: str
    embed_enabled: bool
    embed_model: str
    max_chunks: int
    max_context_chars: int


class IrisWikiSettingsPanel(QWidget):
    """Vault·동기화·임베딩 설정."""

    def __init__(
        self,
        settings: Settings,
        *,
        on_sync_requested: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_sync = on_sync_requested
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Iris Wiki")
        title.setObjectName("PanelTitle")
        lay.addWidget(title)

        form = QFormLayout()
        self._enabled = QCheckBox("Iris Wiki 사용")
        self._enabled.setChecked(bool(settings.wiki_enabled))
        form.addRow("", self._enabled)

        self._vault = QLineEdit()
        vault = settings.wiki_vault_path or str(default_vault_path())
        self._vault.setText(vault)
        form.addRow("Vault 경로", self._vault)

        self._embed = QCheckBox("Ollama 임베딩 (하이브리드 검색)")
        self._embed.setChecked(bool(settings.wiki_embed_enabled))
        form.addRow("", self._embed)

        self._embed_model = QLineEdit()
        self._embed_model.setText(
            getattr(settings, "wiki_embed_model", "") or "nomic-embed-text"
        )
        form.addRow("임베딩 모델", self._embed_model)

        self._max_chunks = QSpinBox()
        self._max_chunks.setRange(1, 24)
        self._max_chunks.setValue(int(settings.wiki_max_chunks))
        form.addRow("LLM 청크 상한", self._max_chunks)

        self._max_chars = QSpinBox()
        self._max_chars.setRange(1000, 48000)
        self._max_chars.setSingleStep(500)
        self._max_chars.setValue(int(settings.wiki_max_context_chars))
        form.addRow("컨텍스트 글자 상한", self._max_chars)

        lay.addLayout(form)

        row = QHBoxLayout()
        self._status = QLabel("")
        self._status.setWordWrap(True)
        row.addWidget(self._status, 1)
        btn_sync = QPushButton("지금 동기화")
        btn_sync.clicked.connect(self._request_sync)
        row.addWidget(btn_sync)
        lay.addLayout(row)

    def set_status_text(self, text: str) -> None:
        self._status.setText(text)

    def _request_sync(self) -> None:
        if callable(self._on_sync):
            self._on_sync()

    def selection(self) -> IrisWikiSettingsSelection:
        return IrisWikiSettingsSelection(
            enabled=self._enabled.isChecked(),
            vault_path=self._vault.text().strip(),
            embed_enabled=self._embed.isChecked(),
            embed_model=self._embed_model.text().strip() or "nomic-embed-text",
            max_chunks=self._max_chunks.value(),
            max_context_chars=self._max_chars.value(),
        )
