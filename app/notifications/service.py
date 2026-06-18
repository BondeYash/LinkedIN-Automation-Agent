"""Notification fan-out.

When a draft enters PENDING, dispatch it to every configured + enabled channel,
attaching signed one-click approve/reject/regenerate links, and record one
`notifications` row per channel (SENT / FAILED). Delivery failures are isolated:
one dead channel never blocks the others or the approval request.
"""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.core.security import create_action_token
from app.models.enums import NotificationChannel, NotificationStatus
from app.models.models import GeneratedPost, Notification
from app.notifications.base import Notifier, NotifyPayload
from app.notifications.email_notifier import EmailNotifier
from app.notifications.log_notifier import LogNotifier
from app.notifications.sheets_notifier import SheetsNotifier
from app.notifications.teams_notifier import TeamsNotifier
from app.notifications.whatsapp_notifier import WhatsAppNotifier
from app.repositories.repos import NotificationRepository

logger = logging.getLogger(__name__)

_ACTIONS = ("approve", "reject", "regenerate")
_BUILDERS = {
    "log": LogNotifier,
    "email": EmailNotifier,
    "teams": TeamsNotifier,
    "sheets": SheetsNotifier,
    "whatsapp": WhatsAppNotifier,
}


def build_notifiers(settings: Settings) -> list[Notifier]:
    """Instantiate the channels named in `notification_channels`, keeping only the
    ones that are actually configured. Always guarantees at least the log channel."""
    wanted = [c.strip().lower() for c in settings.notification_channels.split(",") if c.strip()]
    out: list[Notifier] = []
    for name in wanted:
        builder = _BUILDERS.get(name)
        if builder is None:
            logger.warning("Unknown notification channel %r — ignored", name)
            continue
        notifier = builder() if name == "log" else builder(settings)
        if notifier.enabled():
            out.append(notifier)
        else:
            logger.info("Notification channel %r not configured — skipped", name)
    if not out:
        out.append(LogNotifier())  # never leave a PENDING draft un-notified
    return out


class NotificationService:
    def __init__(
        self,
        notif_repo: NotificationRepository,
        *,
        settings: Settings | None = None,
        notifiers: list[Notifier] | None = None,
    ) -> None:
        self.notif_repo = notif_repo
        self.settings = settings or get_settings()
        self.notifiers = notifiers if notifiers is not None else build_notifiers(self.settings)

    def dispatch(self, post: GeneratedPost) -> list[Notification]:
        payload = NotifyPayload(post=post, preview=self._preview(post), links=self._links(post))
        rows: list[Notification] = []
        for notifier in self.notifiers:
            status = NotificationStatus.SENT
            try:
                notifier.send(payload)
            except Exception:  # one channel failing must not break the others
                status = NotificationStatus.FAILED
                logger.warning("Notifier %s failed for post %s", notifier.channel.value, post.id, exc_info=True)
            rows.append(
                self.notif_repo.create(
                    Notification(post_id=post.id, channel=notifier.channel, status=status)
                )
            )
        return rows

    # --- internals -----------------------------------------------------------

    def _links(self, post: GeneratedPost) -> dict[str, str]:
        base = self.settings.public_base_url.rstrip("/")
        return {
            action: f"{base}/approvals/action?token={create_action_token(post_id=post.id, action=action, settings=self.settings)}"
            for action in _ACTIONS
        }

    @staticmethod
    def _preview(post: GeneratedPost) -> str:
        tags = " ".join(f"#{t}" for t in (post.hashtags or []))
        parts = [
            f"Headline: {post.headline or ''}",
            f"Hook: {post.hook or ''}",
            "",
            post.body,
            "",
            f"CTA: {post.cta or ''}",
            tags,
        ]
        if post.review_notes:
            parts.append(f"\n⚠ Quality flags: {post.review_notes}")
        return "\n".join(parts).strip()
