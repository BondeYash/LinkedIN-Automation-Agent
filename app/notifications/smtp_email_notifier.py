"""SMTP email notifier — the "smtp" channel.

A dependency-free alternative to the Gmail-API EmailNotifier, built for headless
runs (GitHub Actions cron) where an OAuth token file is awkward. Sends over plain
SMTP+STARTTLS with a Gmail App Password (or any SMTP provider). Disabled unless
host/user/password and a recipient are configured, so the app still runs offline.

The message is short: topic + one-line headline + the approve/reject/regenerate
links. The links only act when the agent web app is reachable at PUBLIC_BASE_URL
— in PC-off / Actions-only mode they're for review; you approve from the
dashboard when the app is next up (it shares the same database).
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from app.core.config import Settings, get_settings
from app.models.enums import NotificationChannel
from app.notifications.base import NotifyPayload

logger = logging.getLogger(__name__)


class SmtpEmailNotifier:
    channel = NotificationChannel.EMAIL

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        s = self.settings
        return bool(s.smtp_host and s.smtp_user and s.smtp_password and s.notify_to_email)

    def _html(self, payload: NotifyPayload) -> str:
        post = payload.post
        topic = post.topic.name if post.topic else f"Post #{post.id}"
        headline = (post.headline or "").strip()
        buttons = "".join(
            f'<p><a href="{url}">{label.title()}</a></p>' for label, url in payload.links.items()
        )
        return (
            f"<h3>New post idea #{post.id}</h3>"
            f"<p><b>Topic:</b> {topic}</p>"
            + (f"<p><i>{headline}</i></p>" if headline else "")
            + f"<hr>{buttons}"
            "<p style='color:#888;font-size:12px'>Approve links act when the agent app "
            "is running; otherwise approve from the dashboard later.</p>"
        )

    def send(self, payload: NotifyPayload) -> None:
        s = self.settings
        msg = MIMEText(self._html(payload), "html")
        topic = payload.post.topic.name if payload.post.topic else ""
        msg["Subject"] = f"[LinkedIn Agent] Draft #{payload.post.id} — {topic[:50]}"
        msg["From"] = s.smtp_from or s.smtp_user
        msg["To"] = s.notify_to_email
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as server:
            server.starttls()
            server.login(s.smtp_user, s.smtp_password)
            server.send_message(msg)
