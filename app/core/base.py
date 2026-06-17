"""Abstract base classes — the contracts later modules implement.

These ABCs are the seams that make the system swappable (Strategy pattern):
- a new news source = a new `BaseCollector`,
- a new scoring method = a new `BaseAnalyzer`,
- a new alert channel = a new `BaseNotifier`,
- a new publish target = a new `BasePublisher`.

The rest of the app depends only on these interfaces, never on a concrete
implementation, so anything can be replaced without touching callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseCollector(ABC):
    """Fetches raw items from one external source (RSS, HN, GitHub, ...)."""

    @abstractmethod
    async def fetch(self) -> list[dict[str, Any]]:
        """Return a list of raw items. Must not raise on a single bad item —
        skip and log it so one malformed entry never kills a collection run."""
        raise NotImplementedError


class BaseAnalyzer(ABC):
    """Transforms or scores data (trend scoring, style learning, analytics)."""

    @abstractmethod
    async def analyze(self, data: Any) -> Any:
        """Process `data` and return the analysis result."""
        raise NotImplementedError


class BaseNotifier(ABC):
    """Sends an approval/alert message to one channel (email, Teams, Sheets)."""

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> bool:
        """Deliver `message`. Return True on success; never raise on a single
        channel failure so one dead channel never blocks the others."""
        raise NotImplementedError


class BasePublisher(ABC):
    """Publishes an approved post to an external platform (LinkedIn)."""

    @abstractmethod
    async def publish(self, post: Any) -> Any:
        """Publish `post` and return a platform result (e.g. the post id).
        Implementations MUST reject any post that is not APPROVED."""
        raise NotImplementedError
