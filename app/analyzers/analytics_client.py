"""LinkedIn analytics client — read engagement for a published post.

Official API only. A member access token (the same `w_member_social` token the
publisher uses) can read the *social counts* of a share via the socialActions
endpoint: likes and comments. Shares and impressions live behind the
organization analytics product, which a personal token generally cannot reach —
so those are fetched best-effort and default to 0 rather than failing the sync.

One method, `fetch(share_urn)`, returns a `PostMetrics`. Transient failures
(timeout / 5xx / 429) are retried via the shared policy; a 4xx (bad token,
missing permission) raises so the service can record it and move on.
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

_SOCIAL_PATH = "/v2/socialActions/{urn}"


@dataclass
class PostMetrics:
    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0


class AnalyticsAuthError(RuntimeError):
    """No access token configured — analytics cannot be pulled."""


class LinkedInAnalyticsClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def configured(self) -> bool:
        return bool(self.settings.linkedin_access_token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.linkedin_access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    async def fetch(self, share_urn: str) -> PostMetrics:
        """Pull current engagement for `share_urn` (e.g. urn:li:share:123).

        Raises `AnalyticsAuthError` if unconfigured, or an `httpx` error for a
        non-transient failure after the retry budget is spent.
        """
        if not self.configured():
            raise AnalyticsAuthError("LINKEDIN_ACCESS_TOKEN must be set to pull analytics")

        url = self.settings.linkedin_api_base.rstrip("/") + _SOCIAL_PATH.format(
            urn=quote(share_urn, safe="")
        )
        async with httpx.AsyncClient(timeout=self.settings.linkedin_timeout_seconds) as client:
            payload = await self._get_json(client, url)

        likes, comments = _parse_social(payload)
        return PostMetrics(
            likes=likes,
            comments=comments,
            shares=0,  # not exposed to member tokens — left 0
            impressions=0,  # needs org analytics product — left 0
        )

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


def _parse_social(payload: dict) -> tuple[int, int]:
    """Extract (likes, comments) from a socialActions response, tolerating the
    field-name variations LinkedIn uses across API versions."""
    likes_summary = payload.get("likesSummary") or {}
    comments_summary = payload.get("commentsSummary") or {}
    likes = (
        likes_summary.get("totalLikes")
        or likes_summary.get("aggregatedTotalLikes")
        or 0
    )
    comments = (
        comments_summary.get("aggregatedTotalComments")
        or comments_summary.get("count")
        or 0
    )
    return int(likes), int(comments)
