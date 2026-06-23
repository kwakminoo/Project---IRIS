from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from iris.email.controller import EmailController
from iris.storage.database import Database
from iris.storage.user_profile import UserProfile, save_user_profile

pytestmark = pytest.mark.external_service


def _live_enabled() -> bool:
    return (
        os.getenv("IRIS_ENABLE_LIVE_GOOGLE_WORKSPACE_TESTS") == "1"
        and os.getenv("IRIS_TEST_GOOGLE_EMAIL")
    )


def _send_enabled() -> bool:
    return _live_enabled() and os.getenv("IRIS_ENABLE_LIVE_EMAIL_SEND_TESTS") == "1"


def _controller(tmp_path):
    email = os.environ["IRIS_TEST_GOOGLE_EMAIL"]
    db = Database(tmp_path / "iris-live.db")
    save_user_profile(db, UserProfile(email=email))
    os.environ["USER_GOOGLE_EMAIL"] = email
    EmailController(db).connect_google_workspace()
    return EmailController(db), db


@pytest.mark.skipif(not _send_enabled(), reason="live email send tests disabled")
def test_live_send_self_email(tmp_path) -> None:
    controller, db = _controller(tmp_path)
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"[IRIS LIVE TEST] Self email {ts}"
    data = controller.send_email_direct(
        {
            "to": os.environ["IRIS_TEST_GOOGLE_EMAIL"],
            "subject": subject,
            "body": "Iris Google Workspace email integration self-send test.",
        }
    )
    message_id = str(data.get("id") or data.get("messageId") or "")
    assert controller.verify_sent_email(message_id=message_id or "", query=f'subject:"{subject}"')
    db.close()


@pytest.mark.skipif(not _live_enabled(), reason="live Google Workspace tests disabled")
def test_live_create_and_verify_gmail_draft(tmp_path) -> None:
    controller, db = _controller(tmp_path)
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"[IRIS LIVE TEST] Draft email {ts}"
    data = controller.create_email_draft(
        {
            "to": os.environ["IRIS_TEST_GOOGLE_EMAIL"],
            "subject": subject,
            "body": "Iris draft save verification test.",
        }
    )
    draft_id = str(data.get("id") or data.get("draftId") or "")
    assert draft_id
    verified = controller.verify_email_draft(draft_id)
    assert verified
    print(f"Iris live draft left in Gmail Drafts: {draft_id}")
    db.close()


@pytest.mark.skipif(
    not (
        _send_enabled()
        and os.getenv("IRIS_CONFIRM_EXTERNAL_EMAIL_TEST") == "YES"
        and os.getenv("IRIS_TEST_EXTERNAL_EMAIL")
    ),
    reason="external live email send tests disabled",
)
def test_live_send_external_email(tmp_path) -> None:
    print("WARNING: sending a real external email.")
    controller, db = _controller(tmp_path)
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"[IRIS LIVE TEST] External email {ts}"
    data = controller.send_email_direct(
        {
            "to": os.environ["IRIS_TEST_EXTERNAL_EMAIL"],
            "subject": subject,
            "body": "Iris Google Workspace email integration external send test to Naver address.",
        }
    )
    message_id = str(data.get("id") or data.get("messageId") or "")
    assert controller.verify_sent_email(message_id=message_id or "", query=f'subject:"{subject}"')
    db.close()
