"""Hacker News collector — official Firebase API, no auth.

Reads top-story ids, then fetches each story. Keeps the HN `score` as a
popularity signal for the trend analyzer.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.core.base import BaseCollector
from app.schemas.article import RawArticle
from app.utils.http import transient_retry
from app.utils.text import clean_text

logger = logging.getLogger(__name__)

_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


class HackerNewsCollector(BaseCollector):
    def __init__(self, *, client: httpx.AsyncClient, limit: int = 25) -> None:
        self.client = client
        self.limit = limit

    @transient_retry
    async def _get_json(self, url: str):
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def fetch(self) -> list[RawArticle]:
        try:
            ids = await self._get_json(_TOP)
        except Exception:
            logger.exception("HN top-stories fetch failed")
            return []

        ids = (ids or [])[: self.limit]
        items = await asyncio.gather(
            *(self._fetch_item(i) for i in ids), return_exceptions=True
        )
        out: list[RawArticle] = []
        for item in items:
            if isinstance(item, RawArticle):
                out.append(item)
        return out

    async def _fetch_item(self, story_id: int) -> RawArticle | None:
        story = await self._get_json(_ITEM.format(id=story_id))
        if not story or story.get("type") != "story":
            return None
        title = clean_text(story.get("title"))
        # HN "Ask HN" posts have no url — fall back to the HN discussion link.
        url = story.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        if not title:
            return None
        published = story.get("time")
        return RawArticle(
            source="hackernews",
            title=title,
            url=url,
            content=clean_text(story.get("text")),
            published_at=(
                datetime.fromtimestamp(published, tz=timezone.utc) if published else None
            ),
            raw_signals={"score": story.get("score", 0), "comments": story.get("descendants", 0)},
        )
