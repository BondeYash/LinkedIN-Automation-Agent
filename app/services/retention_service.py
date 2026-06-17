"""Article lifecycle / retention.

Raw articles are an ephemeral working set, not a long-term store. This service
keeps the database small and flat over time:

1. drop heavy `content` text once an article is older than `content_ttl_days`
   (by then it has been scored/embedded — the text adds cost, not value),
2. delete article rows older than `article_ttl_days`,
3. prune the tiny seen-hash dedup memory older than `seen_hash_ttl_days`.

Run daily after collection (the scheduler wires this in Phase 11).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.repositories.repos import ArticleRepository, SeenHashRepository

logger = logging.getLogger(__name__)


@dataclass
class PruneResult:
    content_dropped: int = 0
    articles_deleted: int = 0
    hashes_pruned: int = 0

    def as_dict(self) -> dict:
        return {
            "content_dropped": self.content_dropped,
            "articles_deleted": self.articles_deleted,
            "hashes_pruned": self.hashes_pruned,
        }


class RetentionService:
    def __init__(
        self,
        article_repo: ArticleRepository,
        seen_repo: SeenHashRepository,
        settings: Settings | None = None,
    ) -> None:
        self.article_repo = article_repo
        self.seen_repo = seen_repo
        self.settings = settings or get_settings()

    def run(self) -> PruneResult:
        s = self.settings
        result = PruneResult(
            content_dropped=self.article_repo.drop_content_older_than(s.content_ttl_days),
            articles_deleted=self.article_repo.prune_older_than(s.article_ttl_days),
            hashes_pruned=self.seen_repo.prune_older_than(s.seen_hash_ttl_days),
        )
        self.article_repo.db.commit()
        logger.info(
            "Retention: content_dropped=%d articles_deleted=%d hashes_pruned=%d",
            result.content_dropped,
            result.articles_deleted,
            result.hashes_pruned,
        )
        return result
