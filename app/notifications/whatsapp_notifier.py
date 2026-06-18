"""WhatsApp notifier — sends an approval request over WAHA.

Disabled (skipped) unless both `waha_api_key` and `whatsapp_recipient` are set,
so the app still runs offline. The message is intentionally short — just the
topic (and a one-line headline) plus the one-click approve/reject/regenerate
links, not the full draft — so it reads cleanly on a phone. Tapping "approve"
publishes to LinkedIn straight away when `auto_publish_on_approve` is on.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.models.enums import NotificationChannel
from app.notifications.base import NotifyPayload
from app.notifications.waha_client import is_configured, send_text

_LABELS = {"approve": "✅ Approve", "reject": "❌ Reject", "regenerate": "🔁 Regenerate"}


class WhatsAppNotifier:
    channel = NotificationChannel.WHATSAPP

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        return is_configured(self.settings)

    def send(self, payload: NotifyPayload) -> None:
        send_text(self._render(payload), settings=self.settings)

    @staticmethod
    def _render(payload: NotifyPayload) -> str:
        post = payload.post
        topic = post.topic.name if post.topic else f"Post #{post.id}"
        lines = [
            f"📝 *New post idea #{post.id}*",
            f"*Topic:* {topic}",
        ]
        # One-line headline for context — still not the full draft.
        if post.headline:
            lines.append(f"_{post.headline.strip()}_")
        lines += ["", "— Tap to act —"]
        for action, url in payload.links.items():
            lines.append(f"{_LABELS.get(action, action.title())}: {url}")
        return "\n".join(lines).strip()
