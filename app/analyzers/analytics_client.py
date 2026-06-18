"""LinkedIn analytics client — read REAL engagement for a published post.

Uses the versioned Community Management **memberCreatorPostAnalytics** API, which
the `r_member_postAnalytics` scope unlocks for the authenticated member's OWN
posts — returning impressions, reactions, comments and reshares (the old
`/v2/socialActions` path is deprecated and 403s without org access).

Quirks handled here:
- One metric per call. We fan out one GET per metric (REACTION, COMMENT, RESHARE,
  IMPRESSION) with `aggregation=TOTAL` (lifetime totals) and sum the elements.
- Restli finder syntax: `entity=(share:<url-encoded-urn>)` for a share URN, or
  `(ugc:<url-encoded-urn>)` for a ugcPost URN.
- Requires the `LinkedIn-Version: YYYYMM` header (>= 202506).
- `metricType` comes back as a plain string OR a `{namespace: value}` object
  depending on version, but the `count` field is stable — that's all we read.

`fetch(share_urn)` returns a `PostMetrics`. Transient failures (timeout/5xx/429)
are retried; a non-transient 4xx (bad token / missing scope) raises so the sync
records it and moves on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.core.config import Settings, get_settings
from app.utils.http import is_transient
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_ANALYTICS_PATH = "/rest/memberCreatorPostAnalytics"
# LinkedIn metric -> our PostMetrics field.
_METRICS = {
    "REACTION": "likes",
    "COMMENT": "comments",
    "RESHARE": "shares",
    "IMPRESSION": "impressions",
}


@dataclass
class PostMetrics:
    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0


class AnalyticsAuthError(RuntimeError):
    """No access token configured — analytics cannot be pulled."""


def _entity_param(urn: str) -> str:
    """Build the Restli `entity` value: (share:<enc>) or (ugc:<enc>)."""
    kind = "ugc" if "ugcPost" in urn else "share"
    return f"({kind}:{quote(urn, safe='')})"


class LinkedInAnalyticsClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def configured(self) -> bool:
        return bool(self.settings.linkedin_access_token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.linkedin_access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.settings.linkedin_version,
        }

    async def fetch(self, share_urn: str) -> PostMetrics:
        """Pull lifetime engagement for `share_urn` (e.g. urn:li:share:123).

        Raises `AnalyticsAuthError` if unconfigured, or an `httpx` error for a
        non-transient failure after the retry budget is spent.
        """
        if not self.configured():
            raise AnalyticsAuthError("LINKEDIN_ACCESS_TOKEN must be set to pull analytics")

        base = self.settings.linkedin_api_base.rstrip("/") + _ANALYTICS_PATH
        entity = _entity_param(share_urn)
        metrics = PostMetrics()
        async with httpx.AsyncClient(timeout=self.settings.linkedin_timeout_seconds) as client:
            for metric, field in _METRICS.items():
                url = f"{base}?q=entity&entity={entity}&queryType={metric}&aggregation=TOTAL"
                payload = await self._get_json(client, url)
                setattr(metrics, field, _metric_count(payload))
        return metrics

    async def _get_json(self, client: httpx.AsyncClient, url: str) -> dict:
        """GET with the shared transient-retry policy; raises on fatal 4xx."""
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(is_transient),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            stop=stop_after_attempt(self.settings.publish_max_tries),
            reraise=True,
        ):
            with attempt:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        return {}  # unreachable (reraise=True), keeps type-checkers happy


def _metric_count(payload: dict) -> int:
    """Sum the `count` across all elements (TOTAL → one element, but be safe)."""
    total = 0
    for el in payload.get("elements", []) or []:
        try:
            total += int(el.get("count", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total
