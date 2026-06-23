"""Google Workspace email gateway.

Iris stores account metadata and action audit ids only. Gmail message bodies,
lists, snippets, attachments, and search contents stay in provider responses
and UI memory.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping

from iris.integrations.integration_client import IntegrationClient
from iris.storage.database import Database
from iris.storage.user_profile import load_user_profile

INTEGRATION_NAME = "google_workspace"


@dataclass(frozen=True)
class GoogleWorkspaceAccount:
    id: int
    profile_email: str
    google_email: str
    integration_name: str = INTEGRATION_NAME
    credentials_ref: str = ""
    credentials_dir: str = ""
    is_verified: bool = False
    is_default: bool = False


@dataclass(frozen=True)
class EmailConnectionStatus:
    connected: bool
    message: str
    account: GoogleWorkspaceAccount | None = None


class BodySanitizer(HTMLParser):
    """Small allow-list sanitizer for QTextBrowser HTML rendering."""

    _allowed_tags = {
        "a",
        "b",
        "blockquote",
        "br",
        "div",
        "em",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    }
    _void_tags = {"br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "img":
            return
        if tag in {"script", "style", "iframe", "object", "embed"}:
            self._blocked_depth += 1
            return
        if self._blocked_depth or tag not in self._allowed_tags:
            return
        safe_attrs = []
        if tag == "a":
            for name, value in attrs:
                if name.lower() == "href" and value and value.startswith(("http://", "https://", "mailto:")):
                    safe_attrs.append(f' href="{escape(value, quote=True)}"')
        self.parts.append(f"<{tag}{''.join(safe_attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"img", "script", "style", "iframe", "object", "embed"}:
            return
        if tag in self._allowed_tags:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._blocked_depth:
            if tag in {"script", "style", "iframe", "object", "embed", "img"}:
                self._blocked_depth -= 1
            return
        if tag in self._allowed_tags and tag not in self._void_tags:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._blocked_depth:
            self.parts.append(escape(data))


def sanitize_email_html(raw: str) -> str:
    parser = BodySanitizer()
    parser.feed(raw or "")
    parser.close()
    return "".join(parser.parts)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_target(values: Iterable[str]) -> str:
    joined = ",".join(v.strip().lower() for v in values if v.strip())
    return hashlib.sha256(joined.encode("utf-8")).hexdigest() if joined else ""


class GoogleWorkspaceAccountRegistry:
    def __init__(self, db: Database) -> None:
        self._db = db

    def profile_email(self) -> str:
        return load_user_profile(self._db).email.strip().lower()

    def default_account(self) -> GoogleWorkspaceAccount | None:
        row = self._db._execute(  # noqa: SLF001
            """
            SELECT * FROM google_workspace_accounts
            WHERE is_default=1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        return self._row_to_account(row) if row else None

    def upsert_from_env(self) -> GoogleWorkspaceAccount:
        profile_email = self.profile_email()
        google_email = os.getenv("USER_GOOGLE_EMAIL", "").strip().lower()
        if not profile_email:
            raise ValueError("Iris profile email is empty.")
        if not google_email:
            raise ValueError("USER_GOOGLE_EMAIL is required.")
        if google_email != profile_email:
            raise ValueError("Google email must match Iris profile email.")
        credentials_dir = os.getenv("GOOGLE_MCP_CREDENTIALS_DIR", "").strip()
        ts = _now()
        self._db._execute(  # noqa: SLF001
            """
            INSERT INTO google_workspace_accounts (
                profile_email, google_email, credentials_dir, is_verified,
                is_default, created_at, updated_at
            ) VALUES (?, ?, ?, 1, 1, ?, ?)
            ON CONFLICT(google_email) DO UPDATE SET
                profile_email=excluded.profile_email,
                credentials_dir=excluded.credentials_dir,
                is_verified=1,
                is_default=1,
                updated_at=excluded.updated_at
            """,
            (profile_email, google_email, credentials_dir, ts, ts),
        )
        self._db._commit()  # noqa: SLF001
        return self.default_account() or GoogleWorkspaceAccount(0, profile_email, google_email)

    def status(self) -> EmailConnectionStatus:
        account = self.default_account()
        if account is None:
            return EmailConnectionStatus(False, "Google Workspace connection is not configured.")
        profile_email = self.profile_email()
        if not profile_email:
            return EmailConnectionStatus(False, "Iris profile email is empty.", account)
        if account.google_email.strip().lower() != profile_email:
            return EmailConnectionStatus(False, "Google account email does not match Iris profile email.", account)
        if self._db.get_integration_endpoint(account.integration_name) is None:
            return EmailConnectionStatus(False, "google_workspace integration endpoint is missing.", account)
        return EmailConnectionStatus(True, "Connected", account)

    def log_action(
        self,
        account_id: int | None,
        action_type: str,
        *,
        status: str,
        provider_message_id: str = "",
        provider_draft_id: str = "",
        recipients: Iterable[str] = (),
        error_code: str = "",
    ) -> None:
        self._db._execute(  # noqa: SLF001
            """
            INSERT INTO email_action_audit_logs (
                google_account_id, action_type, provider_message_id,
                provider_draft_id, target_hash, status, error_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                action_type,
                provider_message_id or None,
                provider_draft_id or None,
                _hash_target(recipients) or None,
                status,
                error_code or None,
                _now(),
            ),
        )
        self._db._commit()  # noqa: SLF001

    @staticmethod
    def _row_to_account(row: Mapping[str, Any]) -> GoogleWorkspaceAccount:
        return GoogleWorkspaceAccount(
            id=int(row["id"]),
            profile_email=str(row["profile_email"]),
            google_email=str(row["google_email"]),
            integration_name=str(row["integration_name"] or INTEGRATION_NAME),
            credentials_ref=str(row["credentials_ref"] or ""),
            credentials_dir=str(row["credentials_dir"] or ""),
            is_verified=bool(row["is_verified"]),
            is_default=bool(row["is_default"]),
        )


class GoogleWorkspaceGateway:
    """Thin Gmail MCP gateway with tool discovery."""

    _aliases = {
        "labels": ("gmail_list_labels", "list_gmail_labels", "gmail.labels.list", "gmail_list_email_labels"),
        "list": ("gmail_list_messages", "list_gmail_messages", "gmail.messages.list", "gmail_search"),
        "message": ("gmail_get_message", "get_gmail_message", "gmail.messages.get"),
        "draft": ("gmail_create_draft", "create_gmail_draft", "gmail.drafts.create"),
        "get_draft": ("gmail_get_draft", "get_gmail_draft", "gmail.drafts.get"),
        "send_draft": ("gmail_send_draft", "send_gmail_draft", "gmail.drafts.send"),
        "send": ("gmail_send_message", "send_gmail_message", "gmail.messages.send"),
        "thread": ("gmail_get_thread", "get_gmail_thread", "gmail.threads.get"),
    }

    def __init__(self, db: Database) -> None:
        row = db.get_integration_endpoint(INTEGRATION_NAME)
        if row is None:
            raise ValueError("google_workspace integration endpoint is missing.")
        self._client = IntegrationClient(IntegrationClient.from_row(dict(row)))
        self._tool_names: dict[str, str] = {}

    def discover(self) -> tuple[bool, str]:
        ok, msg, tools = self._client.list_tools()
        if not ok:
            return ok, msg
        names = [str(t.get("name", "")) for t in tools if t.get("name")]
        self._tool_names = {
            key: self._resolve_tool(names, aliases)
            for key, aliases in self._aliases.items()
        }
        return True, msg

    def list_labels(self) -> dict[str, Any]:
        return self._call("labels", {})

    def list_messages(
        self,
        *,
        label: str = "INBOX",
        page_token: str = "",
        page_size: int = 30,
        query: str = "",
    ) -> dict[str, Any]:
        return self._call(
            "list",
            {
                "label": label,
                "labelIds": [label],
                "pageToken": page_token,
                "maxResults": page_size,
                "q": query,
            },
        )

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._call("message", {"id": message_id, "messageId": message_id, "format": "full"})

    def create_draft(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("draft", dict(payload))

    def verify_draft(self, draft_id: str) -> dict[str, Any]:
        return self._call("get_draft", {"id": draft_id, "draftId": draft_id})

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        return self._call("send_draft", {"id": draft_id, "draftId": draft_id})

    def send_direct(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("send", dict(payload))

    def search(self, query: str, *, page_size: int = 30) -> dict[str, Any]:
        return self.list_messages(label="", page_size=page_size, query=query)

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        return self._call("thread", {"id": thread_id, "threadId": thread_id})

    def _call(self, key: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if not self._tool_names:
            ok, msg = self.discover()
            if not ok:
                raise RuntimeError(msg)
        tool = self._tool_names.get(key, "")
        if not tool:
            raise RuntimeError(f"Gmail MCP tool not found for {key}.")
        ok, msg, data = self._client.call_json(tool, params)
        if not ok:
            raise RuntimeError(msg)
        return self._unwrap_result(data)

    @staticmethod
    def _resolve_tool(names: list[str], aliases: tuple[str, ...]) -> str:
        lowered = {n.lower(): n for n in names}
        for alias in aliases:
            if alias.lower() in lowered:
                return lowered[alias.lower()]
        for name in names:
            low = name.lower().replace("-", "_")
            if "gmail" in low and any(part in low for part in aliases[0].split("_")[1:]):
                return name
        return ""

    @staticmethod
    def _unwrap_result(data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, list) and content:
                text = content[0].get("text") if isinstance(content[0], dict) else None
                if isinstance(text, str):
                    try:
                        parsed = json.loads(text)
                        return parsed if isinstance(parsed, dict) else {"result": parsed}
                    except json.JSONDecodeError:
                        return {"text": text}
            result = data.get("result")
            if isinstance(result, dict):
                return result
            return data
        return {"result": data}


def ensure_google_workspace_endpoint_from_env(db: Database) -> None:
    base_url = os.getenv("GOOGLE_WORKSPACE_MCP_URL", "").strip()
    command = os.getenv("GOOGLE_WORKSPACE_MCP_COMMAND", "").strip()
    auth_header = os.getenv("GOOGLE_WORKSPACE_MCP_AUTH_HEADER", "").strip()
    if not base_url and not command:
        return
    db.upsert_integration_endpoint(
        INTEGRATION_NAME,
        kind="mcp",
        base_url=base_url,
        command=command,
        auth_header=auth_header,
        enabled=True,
        notes="Google Workspace MCP endpoint for Iris Mail",
    )
