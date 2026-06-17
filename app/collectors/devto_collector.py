"""Dev.to collector — top articles via the public Forem API.

An API key is optional for reading public articles but lifts rate limits.
Keeps `positive_reactions` and `comments` as popularity signals.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.core.base import BaseCollector
from app.schemas.article import RawArticle
from app.utils.http import transient_retry
from app.utils.text import clean_text

logger = logging.getLogger(__name__)

_ARTICLES = "https://dev.to/api/articles"


class DevToCollector(BaseCollector):
    def __init__(self, *, client: httpx.AsyncClient, api_key: str = "", limit: int = 25) -> None:
        self.client = client
        self.api_key = api_key
        self.limit = limit

    def _headers(self) -> dict[str, str]:
        return {"api-key": self.api_key} if self.api_key else {}

    @transient_retry
    async def _top(self):
        params = {"top": "7", "per_page": str(self.limit)}
        resp = await self.client.get(_ARTICLES, params=params, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def fetch(self) -> list[RawArticle]:
        try:
            articles = await self._top()
        except Exception:
            logger.exception("Dev.to fetch failed")
            return []

        out: list[RawArticle] = []
        for art in (articles or [])[: self.limit]:
            url = art.get("url")
            title = clean_text(art.get("title"))
            if not url or not title:
                continue
            out.append(
                RawArticle(
                    source="devto",
                    title=title,
                    url=url,
                    content=clean_text(art.get("description")),
                    published_at=_iso(art.get("published_at")),
                    raw_signals={
                        "reactions": art.get("positive_reactions_count", 0),
                        "comments": art.get("comments_count", 0),
                        "tags": art.get("tag_list", []),
                    },
                )
            )
        return out


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
