"""Microsoft Teams notifier — posts an approval card to an incoming-webhook URL.

Disabled (skipped) unless `teams_webhook_url` is set, so the app runs offline.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.models.enums import NotificationChannel
from app.notifications.base import NotifyPayload


class TeamsNotifier:
    channel = NotificationChannel.TEAMS

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        return bool(self.settings.teams_webhook_url)

    def send(self, payload: NotifyPayload) -> None:
        actions = [
            {"@type": "OpenUri", "name": label.title(), "targets": [{"os": "default", "uri": url}]}
            for label, url in payload.links.items()
        ]
        card = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": "LinkedIn draft awaiting approval",
            "title": f"Draft #{payload.post.id} awaiting approval",
            "text": payload.preview.replace("\n", "\n\n"),
            "potentialAction": actions,
        }
        resp = httpx.post(self.settings.teams_webhook_url, json=card, timeout=15.0)
        resp.raise_for_status()
