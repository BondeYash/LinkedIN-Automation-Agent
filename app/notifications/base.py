"""Notifier abstraction — one implementation per channel (email, Teams, Sheets,
log). The approval flow fans a PENDING draft out to every enabled notifier; each
is responsible for one delivery mechanism and raises on failure so the service
can record SENT / FAILED per channel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.models.enums import NotificationChannel
from app.models.models import GeneratedPost


@dataclass
class NotifyPayload:
    """Everything a notifier needs to render and deliver one approval request."""

    post: GeneratedPost
    preview: str  # plain-text rendering of the draft
    links: dict[str, str] = field(default_factory=dict)  # action -> one-click URL


@runtime_checkable
class Notifier(Protocol):
    channel: NotificationChannel

    def enabled(self) -> bool:
        """True when this channel is configured well enough to send."""

    def send(self, payload: NotifyPayload) -> None:
        """Deliver the approval request. Raise on failure."""
