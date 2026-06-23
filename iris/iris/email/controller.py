"""Email UI controller."""

from __future__ import annotations

from typing import Any, Mapping

from iris.email.google_workspace import (
    EmailConnectionStatus,
    GoogleWorkspaceAccountRegistry,
    GoogleWorkspaceGateway,
    ensure_google_workspace_endpoint_from_env,
    sanitize_email_html,
)
from iris.storage.database import Database


class EmailController:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._registry = GoogleWorkspaceAccountRegistry(db)

    def get_google_workspace_connection_status(self) -> EmailConnectionStatus:
        ensure_google_workspace_endpoint_from_env(self._db)
        return self._registry.status()

    def connect_google_workspace(self) -> EmailConnectionStatus:
        ensure_google_workspace_endpoint_from_env(self._db)
        self._registry.upsert_from_env()
        return self._registry.status()

    def list_email_labels(self) -> dict[str, Any]:
        self._require_connection()
        return GoogleWorkspaceGateway(self._db).list_labels()

    def list_email_messages(
        self,
        label: str,
        page_token: str = "",
        page_size: int = 30,
        query: str = "",
    ) -> dict[str, Any]:
        self._require_connection()
        return GoogleWorkspaceGateway(self._db).list_messages(
            label=label,
            page_token=page_token,
            page_size=page_size,
            query=query,
        )

    def get_email_message(self, message_id: str) -> dict[str, Any]:
        self._require_connection()
        data = GoogleWorkspaceGateway(self._db).get_message(message_id)
        body = str(data.get("body") or data.get("html") or data.get("text") or "")
        if body:
            data["body"] = sanitize_email_html(body)
        return data

    def create_email_draft(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        account = self._require_connection()
        data = GoogleWorkspaceGateway(self._db).create_draft(payload)
        draft_id = str(data.get("id") or data.get("draftId") or "")
        self._registry.log_action(
            account.id,
            "create_draft",
            status="success" if draft_id else "unknown",
            provider_draft_id=draft_id,
            recipients=self._recipients(payload),
        )
        return data

    def verify_email_draft(self, draft_id: str) -> dict[str, Any]:
        self._require_connection()
        return GoogleWorkspaceGateway(self._db).verify_draft(draft_id)

    def send_email_draft(self, draft_id: str) -> dict[str, Any]:
        account = self._require_connection()
        data = GoogleWorkspaceGateway(self._db).send_draft(draft_id)
        message_id = str(data.get("id") or data.get("messageId") or "")
        self._registry.log_action(
            account.id,
            "send_draft",
            status="success" if message_id else "unknown",
            provider_message_id=message_id,
            provider_draft_id=draft_id,
        )
        return data

    def send_email_direct(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        account = self._require_connection()
        data = GoogleWorkspaceGateway(self._db).send_direct(payload)
        message_id = str(data.get("id") or data.get("messageId") or "")
        self._registry.log_action(
            account.id,
            "send_direct",
            status="success" if message_id else "unknown",
            provider_message_id=message_id,
            recipients=self._recipients(payload),
        )
        return data

    def verify_sent_email(self, message_id: str = "", query: str = "") -> dict[str, Any]:
        self._require_connection()
        if message_id:
            return GoogleWorkspaceGateway(self._db).get_message(message_id)
        return GoogleWorkspaceGateway(self._db).search(query)

    def search_emails(self, query: str) -> dict[str, Any]:
        self._require_connection()
        return GoogleWorkspaceGateway(self._db).search(query)

    def get_email_thread(self, thread_id: str) -> dict[str, Any]:
        self._require_connection()
        return GoogleWorkspaceGateway(self._db).get_thread(thread_id)

    def _require_connection(self):
        status = self.get_google_workspace_connection_status()
        if not status.connected or status.account is None:
            raise RuntimeError(status.message)
        return status.account

    @staticmethod
    def _recipients(payload: Mapping[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("to", "cc", "bcc"):
            raw = payload.get(key, [])
            if isinstance(raw, str):
                values.extend(x.strip() for x in raw.split(","))
            elif isinstance(raw, list):
                values.extend(str(x).strip() for x in raw)
        return [v for v in values if v]
