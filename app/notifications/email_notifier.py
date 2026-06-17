"""Email notifier — sends the draft preview + one-click action links via Gmail API.

Uses previously authorized OAuth user credentials stored as a token JSON file (the
interactive consent is a one-time setup outside the app). Disabled unless both a
recipient and a token file are configured, so the app runs offline.
"""

from __future__ import annotations

import base64
from email.mime.text import MIMEText

from app.core.config import Settings, get_settings
from app.models.enums import NotificationChannel
from app.notifications.base import NotifyPayload

_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class EmailNotifier:
    channel = NotificationChannel.EMAIL

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._service = None

    def enabled(self) -> bool:
        return bool(self.settings.notify_to_email and self.settings.gmail_token_file)

    def _gmail(self):
        if self._service is None:
            from google.oauth2.credentials import Credentials  # lazy imports
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(self.settings.gmail_token_file, _SCOPES)
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    def _body_html(self, payload: NotifyPayload) -> str:
        buttons = "".join(
            f'<p><a href="{url}">{label.title()}</a></p>' for label, url in payload.links.items()
        )
        body = payload.preview.replace("\n", "<br>")
        return f"<h3>Draft #{payload.post.id} awaiting approval</h3><p>{body}</p>{buttons}"

    def send(self, payload: NotifyPayload) -> None:
        msg = MIMEText(self._body_html(payload), "html")
        msg["To"] = self.settings.notify_to_email
        msg["Subject"] = f"[Approval] LinkedIn draft #{payload.post.id}"
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        self._gmail().users().messages().send(userId="me", body={"raw": raw}).execute()
