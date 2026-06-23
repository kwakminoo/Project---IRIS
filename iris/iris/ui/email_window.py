"""Iris internal email workspace."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Mapping

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.email.controller import EmailController
from iris.storage.database import Database


class EmailComposerDialog(QDialog):
    def __init__(self, from_email: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iris Mail Composer")
        self.setMinimumSize(620, 560)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.from_field = QLineEdit(from_email)
        self.from_field.setReadOnly(True)
        self.to_field = QLineEdit()
        self.cc_field = QLineEdit()
        self.bcc_field = QLineEdit()
        self.subject_field = QLineEdit()
        self.body_field = QTextEdit()
        self.body_field.setMinimumHeight(260)
        self.attachments = QLabel("Attachments: disabled in MVP")
        self.ai_button = QPushButton("AI로 다듬기")
        self.ai_button.setEnabled(False)
        self.ai_button.setToolTip("준비 중")
        form.addRow("From", self.from_field)
        form.addRow("To", self.to_field)
        form.addRow("Cc", self.cc_field)
        form.addRow("Bcc", self.bcc_field)
        form.addRow("Subject", self.subject_field)
        form.addRow("Body", self.body_field)
        form.addRow("", self.attachments)
        form.addRow("", self.ai_button)
        root.addLayout(form)
        buttons = QDialogButtonBox()
        self.save_draft_button = buttons.addButton("임시저장", QDialogButtonBox.ButtonRole.ActionRole)
        self.send_button = buttons.addButton("보내기", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("취소", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def payload(self) -> dict[str, Any]:
        return {
            "from": self.from_field.text().strip(),
            "to": self.to_field.text().strip(),
            "cc": self.cc_field.text().strip(),
            "bcc": self.bcc_field.text().strip(),
            "subject": self.subject_field.text().strip(),
            "body": self.body_field.toPlainText(),
            "attachments": [],
        }


class EmailWindow(QWidget):
    back_requested = pyqtSignal()

    _folders = (
        ("INBOX", "받은메일"),
        ("SENT", "보낸메일"),
        ("DRAFT", "임시보관함"),
        ("STARRED", "별표"),
        ("IMPORTANT", "중요"),
        ("ALL", "전체메일"),
    )

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmailWorkspacePage")
        self._controller = EmailController(db)
        self._label = "INBOX"
        self._page_token = ""
        self._page_size = 30
        self._account_email = ""
        self._messages: dict[str, Mapping[str, Any]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QFrame()
        header.setObjectName("TopStatusHeader")
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(0, 0, 0, 8)
        title = QLabel("Iris Mail")
        title.setObjectName("PanelTitle")
        self.account_label = QLabel("Disconnected")
        self.account_label.setObjectName("StatusChipValue")
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search Gmail")
        self.search_field.returnPressed.connect(self._search)
        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self.refresh)
        self.compose_button = QPushButton("새 메일")
        self.compose_button.clicked.connect(self._compose)
        back_button = QPushButton("뒤로")
        back_button.clicked.connect(self.back_requested.emit)
        header_lay.addWidget(title)
        header_lay.addWidget(self.account_label)
        header_lay.addStretch(1)
        header_lay.addWidget(self.search_field, 2)
        header_lay.addWidget(self.refresh_button)
        header_lay.addWidget(self.compose_button)
        header_lay.addWidget(back_button)
        root.addWidget(header)

        self.disconnected_panel = QWidget()
        disconnected_lay = QVBoxLayout(self.disconnected_panel)
        disconnected_lay.addStretch(1)
        self.disconnected_label = QLabel("Google Workspace 연결 필요")
        self.disconnected_label.setObjectName("PanelTitle")
        self.disconnected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        connect_btn = QPushButton("환경변수로 Google Workspace 연결")
        connect_btn.clicked.connect(self._connect)
        disconnected_lay.addWidget(self.disconnected_label)
        disconnected_lay.addWidget(connect_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        disconnected_lay.addStretch(1)
        root.addWidget(self.disconnected_panel, 1)

        self.mail_panel = QSplitter(Qt.Orientation.Horizontal)
        self.mail_panel.setChildrenCollapsible(False)
        self.mail_panel.setHandleWidth(0)
        self.sidebar = QListWidget()
        self.sidebar.setMaximumWidth(180)
        for label, text in self._folders:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, label)
            self.sidebar.addItem(item)
        self.sidebar.currentItemChanged.connect(self._folder_changed)
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._message_selected)
        self.reader = QTextBrowser()
        self.reader.setOpenExternalLinks(False)
        self.reader.setHtml("<p>메일을 선택하세요.</p>")
        self.mail_panel.addWidget(self.sidebar)
        self.mail_panel.addWidget(self.list_widget)
        self.mail_panel.addWidget(self.reader)
        self.mail_panel.setSizes([150, 360, 620])
        root.addWidget(self.mail_panel, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("")
        self.more_button = QPushButton("더 보기")
        self.more_button.clicked.connect(self._load_more)
        footer.addWidget(self.status_label)
        footer.addStretch(1)
        footer.addWidget(self.more_button)
        root.addLayout(footer)
        self._set_connected_ui(False)

    def refresh(self) -> None:
        status = self._controller.get_google_workspace_connection_status()
        self._set_connected_ui(status.connected)
        self._account_email = status.account.google_email if status.account else ""
        self.account_label.setText(self._account_email or status.message)
        if not status.connected:
            self.disconnected_label.setText(status.message)
            return
        self._page_token = ""
        self._load_messages(reset=True)

    def _set_connected_ui(self, connected: bool) -> None:
        self.disconnected_panel.setVisible(not connected)
        self.mail_panel.setVisible(connected)
        self.more_button.setVisible(connected)
        self.refresh_button.setEnabled(True)
        self.compose_button.setEnabled(connected)

    def _connect(self) -> None:
        try:
            status = self._controller.connect_google_workspace()
            self.status_label.setText(status.message)
        except Exception as exc:
            self.status_label.setText(str(exc))
        self.refresh()

    def _folder_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        self._label = str(current.data(Qt.ItemDataRole.UserRole))
        self._page_token = ""
        self._load_messages(reset=True)

    def _search(self) -> None:
        self._page_token = ""
        self._load_messages(reset=True)

    def _load_more(self) -> None:
        self._load_messages(reset=False)

    def _load_messages(self, *, reset: bool) -> None:
        if reset:
            self.list_widget.clear()
            self._messages.clear()
            self.reader.setHtml("<p>Loading...</p>")
        try:
            data = self._controller.list_email_messages(
                self._label,
                page_token=self._page_token,
                page_size=self._page_size,
                query=self.search_field.text().strip(),
            )
            self._page_token = str(data.get("nextPageToken") or data.get("next_page_token") or "")
            messages = _extract_messages(data)
            if not messages and reset:
                self.reader.setHtml("<p>메일이 없습니다.</p>")
            for msg in messages:
                message_id = str(msg.get("id") or msg.get("messageId") or "")
                if not message_id:
                    continue
                self._messages[message_id] = msg
                item = QListWidgetItem(_message_title(msg))
                item.setData(Qt.ItemDataRole.UserRole, message_id)
                self.list_widget.addItem(item)
            self.more_button.setEnabled(bool(self._page_token))
            self.status_label.setText(f"{len(messages)} loaded")
        except Exception as exc:
            self.reader.setHtml(f"<p>Error: {str(exc)}</p>")
            self.status_label.setText(str(exc))

    def _message_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        message_id = str(current.data(Qt.ItemDataRole.UserRole))
        self.reader.setHtml("<p>Loading message...</p>")
        try:
            msg = self._controller.get_email_message(message_id)
            self.reader.setHtml(_render_message(msg))
        except Exception as exc:
            self.reader.setHtml(f"<p>Error: {str(exc)}</p>")

    def _compose(self) -> None:
        dlg = EmailComposerDialog(self._account_email, self)
        dlg.save_draft_button.clicked.connect(lambda: self._save_draft(dlg))
        dlg.send_button.clicked.connect(lambda: self._confirm_send(dlg))
        dlg.exec()

    def _save_draft(self, dlg: EmailComposerDialog) -> None:
        try:
            data = self._controller.create_email_draft(dlg.payload())
            draft_id = str(data.get("id") or data.get("draftId") or "")
            if draft_id:
                self._controller.verify_email_draft(draft_id)
            self.status_label.setText("Gmail 임시보관함에 저장됨")
            dlg.accept()
            self._label = "DRAFT"
            self._load_messages(reset=True)
        except Exception as exc:
            QMessageBox.warning(self, "Draft failed", str(exc))

    def _confirm_send(self, dlg: EmailComposerDialog) -> None:
        payload = dlg.payload()
        preview = payload["body"][:500]
        text = (
            f"From: {payload['from']}\nTo: {payload['to']}\nCc/Bcc: {payload['cc']} {payload['bcc']}\n"
            f"Subject: {payload['subject']}\nAttachments: none\nRisk: external send\n\n{preview}"
        )
        if QMessageBox.question(self, "메일 전송 확인", text) != QMessageBox.StandardButton.Yes:
            return
        try:
            data = self._controller.send_email_direct(payload)
            message_id = str(data.get("id") or data.get("messageId") or "")
            if message_id:
                self._controller.verify_sent_email(message_id=message_id)
            self.status_label.setText("전송 확인 완료")
            dlg.accept()
            self._label = "SENT"
            self._load_messages(reset=True)
        except Exception as exc:
            QMessageBox.warning(self, "Send failed", str(exc))


def _extract_messages(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("messages", "items", "results"):
        val = data.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, Mapping)]
    result = data.get("result")
    if isinstance(result, Mapping):
        return _extract_messages(result)
    return []


def _message_title(msg: Mapping[str, Any]) -> str:
    sender = str(msg.get("from") or msg.get("sender") or "")
    subject = str(msg.get("subject") or "(no subject)")
    snippet = str(msg.get("snippet") or "")
    date = str(msg.get("date") or msg.get("internalDate") or "")
    if date.isdigit():
        date = datetime.fromtimestamp(int(date) / 1000).strftime("%Y-%m-%d %H:%M")
    unread = "* " if "UNREAD" in str(msg.get("labelIds") or "") else ""
    attach = " [attachment]" if msg.get("hasAttachments") else ""
    return f"{unread}{sender}\n{subject}{attach}\n{snippet}\n{date}"


def _render_message(msg: Mapping[str, Any]) -> str:
    subject = escape(str(msg.get("subject") or "(no subject)"))
    sender = escape(str(msg.get("from") or msg.get("sender") or ""))
    to = escape(str(msg.get("to") or ""))
    date = escape(str(msg.get("date") or ""))
    body = str(msg.get("body") or msg.get("html") or msg.get("text") or "")
    attachments = msg.get("attachments") if isinstance(msg.get("attachments"), list) else []
    attachment_lines = "".join(f"<li>{escape(str(a))}</li>" for a in attachments)
    return (
        f"<h2>{subject}</h2><p><b>From:</b> {sender}<br><b>To:</b> {to}<br><b>Date:</b> {date}</p>"
        f"<hr>{body}<hr><p><button disabled>답장</button> <button disabled>전달</button> "
        f"<button disabled>요약</button> <button disabled title='준비 중'>일정으로 추가</button></p>"
        f"<h3>Attachments</h3><ul>{attachment_lines}</ul>"
    )
