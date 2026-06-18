"""Analytics service — pull engagement for published posts and store it.

For every post that was successfully published, ask LinkedIn for its current
likes/comments/shares/impressions and **append** an `analytics` row stamped with
`captured_at`. Rows are never overwritten, so each sync grows a time-series and
trends stay visible.

One post failing to fetch (expired token, deleted share, missing permission)
never aborts the run — it is logged and skipped so the rest still sync.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.analyzers.analytics_client import LinkedInAnalyticsClient, PostMetrics
from app.core.config import Settings, get_settings
from app.models.models import Analytics
from app.repositories.repos import AnalyticsRepository, PublishingRepository

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    synced: int = 0
    skipped: int = 0
    errors: int = 0


def engagement_rate(metrics: PostMetrics | Analytics, settings: Settings) -> float:
    """eng_rate = (likes + w_comment·comments + w_share·shares) / impressions.

    When impressions are unavailable (member tokens can't read them) we divide by
    `analytics_assumed_impressions` if set, else return 0.0 — never divide by zero.
    """
    weighted = (
        metrics.likes
        + settings.eng_weight_comment * metrics.comments
        + settings.eng_weight_share * metrics.shares
    )
    impressions = metrics.impressions or settings.analytics_assumed_impressions
    if impressions <= 0:
        return 0.0
    return round(weighted / impressions, 4)


class AnalyticsService:
    def __init__(
        self,
        analytics: AnalyticsRepository,
        publishing: PublishingRepository,
        client: LinkedInAnalyticsClient | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.analytics = analytics
        self.publishing = publishing
        self.settings = settings or get_settings()
        self.client = client or LinkedInAnalyticsClient(self.settings)

    async def sync(self) -> SyncResult:
        """Pull fresh metrics for every published post; append one row each."""
        published = self.publishing.published_post_ids()
        result = SyncResult()

        for post_id, urn in list(published.items())[: self.settings.analytics_max_posts]:
            if not urn:
                result.skipped += 1
                continue
            try:
                metrics = await self.client.fetch(urn)
            except Exception as exc:  # one bad post must not abort the whole sync
                logger.warning("Analytics fetch failed for post %s (%s): %s", post_id, urn, exc)
                result.errors += 1
                continue
            self.analytics.add(
                post_id,
                likes=metrics.likes,
                comments=metrics.comments,
                shares=metrics.shares,
                impressions=metrics.impressions,
            )
            result.synced += 1

        self.analytics.db.commit()
        logger.info(
            "Analytics sync: %d synced, %d skipped, %d errors",
            result.synced, result.skipped, result.errors,
        )
        return result
