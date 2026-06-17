"""Reddit collector — hot posts from chosen subreddits via PRAW.

PRAW is synchronous, so the blocking calls run in a threadpool via
`asyncio.to_thread`. Without credentials the collector logs and returns [] so a
missing key never breaks a collection run. `score` is kept as a popularity
signal.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.base import BaseCollector
from app.schemas.article import RawArticle
from app.utils.text import clean_text

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        user_agent: str,
        subreddits: list[str],
        limit: int = 25,
        reddit=None,  # injectable praw.Reddit for tests
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.subreddits = subreddits
        self.limit = limit
        self._reddit = reddit

    def _get_reddit(self):
        if self._reddit is not None:
            return self._reddit
        if not (self.client_id and self.client_secret):
            return None
        import praw  # imported lazily so the dep is only needed when configured

        self._reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
            check_for_async=False,
        )
        return self._reddit

    def _fetch_sync(self) -> list[RawArticle]:
        reddit = self._get_reddit()
        if reddit is None:
            logger.info("Reddit collector skipped — no credentials configured")
            return []

        per_sub = max(1, self.limit // max(1, len(self.subreddits)))
        out: list[RawArticle] = []
        for sub in self.subreddits:
            try:
                for post in reddit.subreddit(sub).hot(limit=per_sub):
                    if getattr(post, "stickied", False):
                        continue
                    title = clean_text(getattr(post, "title", ""))
                    url = getattr(post, "url", None)
                    if not title or not url:
                        continue
                    created = getattr(post, "created_utc", None)
                    out.append(
                        RawArticle(
                            source="reddit",
                            title=title,
                            url=url,
                            content=clean_text(getattr(post, "selftext", "")),
                            published_at=(
                                datetime.fromtimestamp(created, tz=timezone.utc)
                                if created
                                else None
                            ),
                            raw_signals={
                                "score": getattr(post, "score", 0),
                                "comments": getattr(post, "num_comments", 0),
                                "subreddit": sub,
                            },
                        )
                    )
            except Exception:
                logger.exception("Reddit fetch failed for r/%s", sub)
        return out

    async def fetch(self) -> list[RawArticle]:
        return await asyncio.to_thread(self._fetch_sync)
