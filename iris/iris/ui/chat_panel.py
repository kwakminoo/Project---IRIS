"""채팅 패널."""

from __future__ import annotations

import html
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QTextCursor
from PyQt6.QtWidgets import (
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.ui.command_dock import CommandDock
from iris.ui.chat_display import (
    TYPING_CHARS_PER_TICK,
    TYPING_INTERVAL_MS,
    TYPING_SPEECH_MAX_CHARS_PER_TICK,
    chat_body_to_html,
    effective_typing_duration_ms,
    extend_typing_timeline_ms,
    markdown_to_chat_html,
    normalize_chat_body,
    scale_typing_duration_ms,
    typing_body_to_html,
    typing_target_index,
    visible_typing_text,
)
from iris.ui.theme_tokens import TOKENS


class ChatPanel(QWidget):
    send_clicked = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChatPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._log = QTextEdit()
        self._log.setObjectName("ChatLog")
        self._log.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._log.setReadOnly(True)
        self._log.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        # 스크롤바는 숨기고 마우스 휠로만 스크롤
        self._log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent = QColor(0, 0, 0, 0)
        log_pal = self._log.palette()
        log_pal.setColor(QPalette.ColorRole.Base, transparent)
        log_pal.setColor(QPalette.ColorRole.Window, transparent)
        self._log.setPalette(log_pal)
        self._log.setMinimumHeight(80)
        self._log.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._log.setStyleSheet(
            """
            QTextEdit#ChatLog {
                background: transparent;
                border: none;
                padding: 8px 4px;
            }
            """
        )
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(TYPING_INTERVAL_MS)
        self._typing_timer.timeout.connect(self._type_next_chunk)
        self._typing_text = ""
        self._typing_index = 0
        self._typing_speech_sync = False
        self._typing_speech_duration_ms: float | None = None
        self._typing_speech_start: float | None = None
        self._stream_active = False
        self._stream_who = "Iris"
        self._stream_block_start: int | None = None
        self._typing_body_start: int | None = None
        self._typing_render_markdown = False
        self._user_listening_active = False
        self._command_dock = CommandDock()
        self._input = self._command_dock.input
        self._waveform = self._command_dock.waveform
        self._command_dock.send_clicked.connect(self.send_clicked.emit)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(TOKENS.spacing_sm)
        root.addWidget(self._log, 1)
        root.addWidget(self._command_dock, 0)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(
            self._log.minimumHeight() + self._command_dock.minimumHeight() + TOKENS.spacing_sm
        )

    @property
    def command_dock(self) -> CommandDock:
        return self._command_dock

    def _scroll_log_to_bottom(self, *, deferred: bool = False) -> None:
        """새 메시지·음성 인식 결과가 항상 보이도록 출력창을 맨 아래로 스크롤."""

        def _do_scroll() -> None:
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._log.setTextCursor(cursor)
            self._log.ensureCursorVisible()
            bar = self._log.verticalScrollBar()
            bar.setValue(bar.maximum())

        if deferred:
            QTimer.singleShot(0, _do_scroll)
        else:
            _do_scroll()

    def set_mic_level(self, level: float) -> None:
        """상시 듣기 마이크 레벨 — 하단 주파수 바에 반영."""
        self._command_dock.set_mic_level(level)

    def set_speech_threshold_rms(self, speech_rms: float) -> None:
        """인식 감도 임계 — 점선 위치 갱신."""
        self._command_dock.set_speech_threshold_rms(speech_rms)

    def set_voice_state(self, label: str, *, kind: str = "idle") -> None:
        self._command_dock.set_voice_state(label, kind=kind)

    def begin_user_listening(self) -> None:
        """발화 시작 — 플레이스홀더로 즉시 피드백."""
        self.finish_typing()
        self._remove_user_listening_line()
        self._log.append("<b>나</b>: <i style='color:#94a3b8'>…</i>")
        self._user_listening_active = True
        self._scroll_log_to_bottom(deferred=True)

    def set_user_listening_status(self, status: str) -> None:
        """STT 진행 등 상태 문구 갱신."""
        if not self._user_listening_active:
            self.begin_user_listening()
        self._remove_user_listening_line()
        safe = html.escape(status)
        self._log.append(f"<b>나</b>: <i style='color:#94a3b8'>{safe}</i>")
        self._user_listening_active = True
        self._scroll_log_to_bottom(deferred=True)

    def cancel_user_listening(self) -> None:
        """인식 취소·게이트 거부 시 플레이스홀더 제거."""
        if self._user_listening_active:
            self._remove_user_listening_line()
        self._user_listening_active = False

    def complete_user_message_typed(self, text: str) -> None:
        """음성 인식 완료 — 플레이스홀더 제거 후 본문 즉시 표시."""
        self.cancel_user_listening()
        self.append_message_instant("나", text)

    @property
    def typing_buffer_text(self) -> str:
        """버퍼·스트림 중 누적 본문 (TTS 동기화용)."""
        return self._typing_text

    def append_message(self, who: str, text: str) -> None:
        """Iris 등 — 타이핑 효과로 출력 (TTS 동기화 없음)."""
        self.append_message_typed(who, text, speech_sync=False)

    def append_message_instant(self, who: str, text: str) -> None:
        """사용자 입력 등 — 타이핑 없이 본문 전체를 즉시 표시."""
        self.finish_typing()
        body = normalize_chat_body(who, text)
        if not body:
            return
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._log.toPlainText().strip():
            cursor.insertBlock()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        if who.strip().lower() == "iris":
            cursor.insertHtml(markdown_to_chat_html(body))
        else:
            cursor.insertHtml(chat_body_to_html(body))
        self._log.setTextCursor(cursor)
        self._scroll_log_to_bottom()

    def begin_stream_message(self, who: str) -> None:
        """LLM 스트리밍 — 헤더만 표시, 본문은 버퍼에 쌓고 TTS 시작 시 타이핑."""
        self.finish_typing()
        self._stream_active = True
        self._stream_who = who
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._log.toPlainText().strip():
            cursor.insertBlock()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        self._stream_block_start = cursor.position()
        self._typing_body_start = cursor.position()
        self._typing_render_markdown = who.strip().lower() == "iris"
        self._log.setTextCursor(cursor)
        self._typing_text = ""
        self._typing_index = 0
        self._typing_speech_sync = True
        self._typing_speech_duration_ms = None
        self._typing_speech_start = None
        self._typing_timer.stop()
        self._scroll_log_to_bottom()

    def append_stream_chunk(self, text: str) -> None:
        """스트리밍 청크 — 화면이 아닌 타이핑 버퍼에만 누적."""
        if not text:
            return
        if not self._stream_active:
            self.begin_stream_message("Iris")
        self._append_typing_buffer(text)

    def end_stream_message(self, final_text: str | None = None) -> None:
        """스트림 종료 — 정규화 본문으로 버퍼 확정 (화면 재삽입 없음)."""
        if not self._stream_active:
            if final_text:
                self.append_message("Iris", final_text)
            return
        who = getattr(self, "_stream_who", "Iris")
        if final_text is not None:
            self._finalize_typing_buffer(who, final_text)
        self._stream_active = False
        self._stream_block_start = None
        self._ensure_buffered_typing_fallback()
        self._scroll_log_to_bottom(deferred=True)

    def append_message_typed(
        self,
        who: str,
        text: str,
        *,
        speech_sync: bool = False,
    ) -> None:
        """한 글자씩 표시. Iris + speech_sync면 TTS 재생 시작 후 sync_typing_to_speech 호출."""
        self.finish_typing()
        body = normalize_chat_body(who, text)
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._log.toPlainText().strip():
            cursor.insertBlock()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        self._typing_body_start = cursor.position()
        self._typing_render_markdown = who.strip().lower() == "iris"
        self._log.setTextCursor(cursor)
        self._typing_text = body
        self._typing_index = 0
        self._typing_speech_sync = speech_sync
        self._typing_speech_duration_ms = None
        self._typing_speech_start = None
        if speech_sync:
            self._typing_timer.stop()
        else:
            self._typing_timer.setInterval(TYPING_INTERVAL_MS)
            self._typing_timer.start()
        self._scroll_log_to_bottom()

    def sync_typing_to_speech(
        self,
        duration_ms: float,
        *,
        visible_len: int | None = None,
        spoken_len: int | None = None,
    ) -> None:
        """TTS 재생 길이에 맞춰 대기 중인 본문 타이핑을 시작한다."""
        if not self._typing_text or not self._typing_speech_sync:
            return
        text_len = visible_len if visible_len is not None else len(self._typing_text)
        if spoken_len is not None and spoken_len > 0:
            scaled = scale_typing_duration_ms(duration_ms, text_len, spoken_len)
        else:
            scaled = float(duration_ms)
        self._typing_speech_duration_ms = effective_typing_duration_ms(
            len(self._typing_text),
            scaled,
        )
        self._typing_speech_start = None
        self._typing_timer.setInterval(TYPING_INTERVAL_MS)
        if not self._typing_timer.isActive():
            self._typing_timer.start()

    def extend_typing_for_speech_segment(
        self,
        spoken: str,
        duration_ms: float,
    ) -> None:
        """후속 TTS 세그먼트 — 타이핑 타임라인 예산을 이어서 확장."""
        if not self._typing_text or not self._typing_speech_sync:
            return
        remaining = len(self._typing_text) - self._typing_index
        if remaining <= 0:
            return
        spoken_len = max(len((spoken or "").strip()), 1)
        scaled = scale_typing_duration_ms(duration_ms, remaining, spoken_len)
        if self._typing_speech_start is None:
            self.sync_typing_to_speech(
                duration_ms,
                visible_len=remaining,
                spoken_len=spoken_len,
            )
            return
        elapsed_ms = (time.monotonic() - self._typing_speech_start) * 1000.0
        self._typing_speech_duration_ms = extend_typing_timeline_ms(
            elapsed_ms,
            remaining,
            scaled,
        )

    def on_speech_typing_finished(self, *, flush: bool = True) -> None:
        """TTS 종료·중단 시 남은 글자를 즉시 표시 (다구간 TTS는 flush=False)."""
        if flush and self._typing_speech_sync:
            self.finish_typing()

    def finish_typing(self) -> None:
        """진행 중인 타이핑 효과를 즉시 완료한다."""
        if not self._typing_timer.isActive() and not self._typing_text:
            return
        self._typing_timer.stop()
        if self._typing_render_markdown and self._typing_body_start is not None:
            self._render_markdown_body()
        elif self._typing_index < len(self._typing_text):
            self._typing_index = len(self._typing_text)
            self._replace_typing_body()
        self._typing_text = ""
        self._typing_index = 0
        self._typing_speech_sync = False
        self._typing_speech_duration_ms = None
        self._typing_speech_start = None
        self._typing_body_start = None
        self._typing_render_markdown = False
        self._scroll_log_to_bottom()

    def _remove_user_listening_line(self) -> None:
        """마지막 '나: …' 플레이스홀더 블록 제거."""
        plain = self._log.toPlainText()
        if not plain.strip():
            return
        lines = plain.split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].startswith("나:"):
            lines.pop()
        self._log.setPlainText("\n".join(lines))
        if lines:
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._log.setTextCursor(cursor)
            self._scroll_log_to_bottom()

    def _append_typing_buffer(self, chunk: str) -> None:
        """타이핑 버퍼만 확장 — 스트리밍 중 화면에는 아직 표시하지 않음."""
        if not chunk:
            return
        old_len = len(self._typing_text)
        self._typing_text += chunk
        if (
            self._typing_speech_sync
            and self._typing_speech_duration_ms
            and self._typing_speech_start is not None
            and old_len > 0
        ):
            new_len = len(self._typing_text)
            if new_len > old_len:
                self._typing_speech_duration_ms *= new_len / old_len

    def _finalize_typing_buffer(self, who: str, final_text: str) -> None:
        """스트림 종료 시 정규화 본문으로 버퍼 확정."""
        body = normalize_chat_body(who, final_text)
        old = self._typing_text
        self._typing_text = body
        if self._typing_index > len(body):
            self._typing_index = len(body)
        if self._typing_speech_sync and self._typing_speech_duration_ms and old:
            self._typing_speech_duration_ms *= len(body) / max(len(old), 1)

    def _ensure_buffered_typing_fallback(self) -> None:
        """TTS가 시작되지 않은 스트림 — 일반 타이핑으로 폴백."""
        if (
            not self._typing_text
            or not self._typing_speech_sync
            or self._typing_speech_duration_ms is not None
            or self._typing_timer.isActive()
        ):
            return
        self._typing_speech_sync = False
        self._typing_timer.setInterval(TYPING_INTERVAL_MS)
        self._typing_timer.start()

    def _replace_typing_body(self) -> None:
        """타이핑 본문 영역을 현재 인덱스까지의 평문으로 갱신."""
        if self._typing_body_start is None:
            return
        visible = visible_typing_text(
            self._typing_text,
            self._typing_index,
            render_markdown=self._typing_render_markdown,
        )
        cursor = self._log.textCursor()
        cursor.setPosition(self._typing_body_start)
        cursor.movePosition(
            QTextCursor.MoveOperation.End,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        if visible:
            cursor.insertHtml(typing_body_to_html(visible))
        self._log.setTextCursor(cursor)

    def _render_markdown_body(self) -> None:
        """타이핑 완료 후 마크다운 원문을 렌더링된 HTML로 교체."""
        if self._typing_body_start is None or not self._typing_text:
            return
        cursor = self._log.textCursor()
        cursor.setPosition(self._typing_body_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(markdown_to_chat_html(self._typing_text))
        self._log.setTextCursor(cursor)

    def _type_next_chunk(self) -> None:
        if self._typing_index >= len(self._typing_text):
            self._typing_timer.stop()
            if self._typing_render_markdown and self._typing_body_start is not None:
                self._render_markdown_body()
            self._typing_text = ""
            self._typing_index = 0
            self._typing_speech_sync = False
            self._typing_speech_duration_ms = None
            self._typing_speech_start = None
            self._typing_body_start = None
            self._typing_render_markdown = False
            return

        if self._typing_speech_sync and self._typing_speech_duration_ms:
            if self._typing_speech_start is None:
                self._typing_speech_start = time.monotonic()
            elapsed_ms = (time.monotonic() - self._typing_speech_start) * 1000.0
            target_index = typing_target_index(
                len(self._typing_text),
                elapsed_ms,
                self._typing_speech_duration_ms,
            )
            if target_index <= self._typing_index:
                return
            # TTS 타임라인을 따르되 한 틱에 너무 많이 점프하지 않게 제한
            self._typing_index = min(
                target_index,
                self._typing_index + TYPING_SPEECH_MAX_CHARS_PER_TICK,
            )
        else:
            self._typing_index = min(
                len(self._typing_text),
                self._typing_index + TYPING_CHARS_PER_TICK,
            )

        self._replace_typing_body()
        self._scroll_log_to_bottom()
