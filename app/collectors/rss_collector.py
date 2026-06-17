"""RSS/Atom collector — works for any feed (TechCrunch, The Verge, Google News).

httpx fetches the raw feed bytes (so the network call is retryable and mockable);
feedparser does the parsing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

from app.core.base import BaseCollector
from app.schemas.article import RawArticle
from app.utils.http import transient_retry
from app.utils.text import clean_text

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    def __init__(
        self,
        feed_url: str,
        *,
        source_name: str,
        client: httpx.AsyncClient,
        limit: int = 25,
    ) -> None:
        self.feed_url = feed_url
        self.source_name = source_name
        self.client = client
        self.limit = limit

    @transient_retry
    async def _get(self) -> bytes:
        resp = await self.client.get(self.feed_url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    async def fetch(self) -> list[RawArticle]:
        try:
            content = await self._get()
        except Exception:
            logger.exception("RSS fetch failed for %s", self.source_name)
            return []

        parsed = feedparser.parse(content)
        out: list[RawArticle] = []
        for entry in parsed.entries[: self.limit]:
            link = entry.get("link")
            title = clean_text(entry.get("title"))
            if not link or not title:
                continue
            out.append(
                RawArticle(
                    source=self.source_name,
                    title=title,
                    url=link,
                    content=clean_text(entry.get("summary")),
                    published_at=_entry_time(entry),
                )
            )
        return out


def _entry_time(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
