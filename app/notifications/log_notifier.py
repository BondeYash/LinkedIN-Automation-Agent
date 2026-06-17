"""Always-available fallback notifier — writes the approval request to the log.

Lets the whole approval pipeline run offline with zero external credentials. In
production it sits alongside the real channels as a durable audit trail.
"""

from __future__ import annotations

import logging

from app.models.enums import NotificationChannel
from app.notifications.base import NotifyPayload

logger = logging.getLogger("app.notifications")


class LogNotifier:
    channel = NotificationChannel.LOG

    def enabled(self) -> bool:
        return True

    def send(self, payload: NotifyPayload) -> None:
        links = " ".join(f"{k}={v}" for k, v in payload.links.items())
        logger.info(
            "[APPROVAL] post=%s status=%s\n%s\nActions: %s",
            payload.post.id, payload.post.status.value, payload.preview, links,
        )
