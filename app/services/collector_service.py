"""Collector orchestration: run every source, normalize, dedup, persist.

- runs all collectors concurrently (bounded by a semaphore) so one slow or
  broken source never blocks the others,
- two-level dedup: exact `url_hash` then fuzzy title (rapidfuzz),
- saves only genuinely new articles.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx
from rapidfuzz import fuzz

from app.core.base import BaseCollector
from app.core.config import Settings, get_settings
from app.collectors.devto_collector import DevToCollector
from app.collectors.github_collector import GitHubCollector
from app.collectors.hackernews_collector import HackerNewsCollector
from app.collectors.reddit_collector import RedditCollector
from app.collectors.rss_collector import RSSCollector
from app.models.models import Article
from app.repositories.repos import ArticleRepository, SeenHashRepository
from app.schemas.article import RawArticle
from app.utils.text import url_hash
from seed.sources import DEFAULT_SOURCES

logger = logging.getLogger(__name__)


@dataclass
class CollectResult:
    collected: int = 0  # raw items returned by all collectors
    new: int = 0  # genuinely new articles saved
    duplicates: int = 0  # dropped by url/title dedup
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "collected": self.collected,
            "new": self.new,
            "duplicates": self.duplicates,
            "errors": self.errors,
        }


class CollectorService:
    def __init__(
        self,
        article_repo: ArticleRepository,
        collectors: list[BaseCollector],
        *,
        seen_repo: SeenHashRepository | None = None,
        max_concurrency: int = 5,
        title_threshold: int = 90,
    ) -> None:
        self.article_repo = article_repo
        self.seen_repo = seen_repo
        self.collectors = collectors
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.title_threshold = title_threshold

    async def _run_one(self, collector: BaseCollector) -> list[RawArticle]:
        async with self.semaphore:
            return await collector.fetch()

    async def collect(self) -> CollectResult:
        result = CollectResult()

        gathered = await asyncio.gather(
            *(self._run_one(c) for c in self.collectors),
            return_exceptions=True,
        )

        raw_items: list[RawArticle] = []
        for collector, outcome in zip(self.collectors, gathered):
            if isinstance(outcome, Exception):
                msg = f"{type(collector).__name__}: {outcome}"
                logger.error("Collector failed — %s", msg)
                result.errors.append(msg)
                continue
            raw_items.extend(outcome)

        result.collected = len(raw_items)

        # Seed the fuzzy set with recent DB titles so we dedup against history too.
        seen_hashes: set[str] = set()
        kept_titles: list[str] = self.article_repo.recent_titles(limit=500)

        for item in raw_items:
            h = url_hash(item.url)

            # Level 1 — exact URL hash. Check the durable seen-hash memory (which
            # outlives pruned articles) so old news is never re-ingested; fall
            # back to the articles table if no seen-repo is wired.
            already_seen = h in seen_hashes or (
                self.seen_repo.exists(h)
                if self.seen_repo is not None
                else self.article_repo.exists_url_hash(h)
            )
            if already_seen:
                result.duplicates += 1
                continue

            # Level 2 — fuzzy title match against everything kept so far.
            if self._is_fuzzy_dup(item.title, kept_titles):
                result.duplicates += 1
                continue

            self.article_repo.create(
                Article(
                    source=item.source,
                    url=item.url,
                    url_hash=h,
                    title=item.title,
                    content=item.content,
                    published_at=item.published_at,
                )
            )
            if self.seen_repo is not None:
                self.seen_repo.record(h, item.source)
            seen_hashes.add(h)
            kept_titles.append(item.title)
            result.new += 1

        self.article_repo.db.commit()
        logger.info(
            "Collection done: collected=%d new=%d duplicates=%d errors=%d",
            result.collected,
            result.new,
            result.duplicates,
            len(result.errors),
        )
        return result

    def _is_fuzzy_dup(self, title: str, existing: list[str]) -> bool:
        for other in existing:
            if fuzz.token_set_ratio(title, other) >= self.title_threshold:
                return True
        return False


def build_default_collectors(
    client: httpx.AsyncClient, settings: Settings | None = None
) -> list[BaseCollector]:
    """Wire collectors from the static source list + settings.

    Shares one async HTTP client across the HTTP-based collectors. Reddit uses
    PRAW and only activates when credentials are present.
    """

    settings = settings or get_settings()
    limit = settings.collector_per_source_limit
    collectors: list[BaseCollector] = []

    for src in DEFAULT_SOURCES:
        kind = src["kind"]
        if kind == "rss":
            collectors.append(
                RSSCollector(src["url"], source_name=src["name"], client=client, limit=limit)
            )
        elif kind == "hackernews":
            collectors.append(HackerNewsCollector(client=client, limit=limit))
        elif kind == "github":
            collectors.append(
                GitHubCollector(client=client, token=settings.github_token, limit=limit)
            )
        elif kind == "devto":
            collectors.append(
                DevToCollector(client=client, api_key=settings.devto_api_key, limit=limit)
            )
        elif kind == "reddit":
            collectors.append(
                RedditCollector(
                    client_id=settings.reddit_client_id,
                    client_secret=settings.reddit_client_secret,
                    user_agent=settings.reddit_user_agent,
                    subreddits=[s.strip() for s in settings.reddit_subreddits.split(",") if s.strip()],
                    limit=limit,
                )
            )

    return collectors
