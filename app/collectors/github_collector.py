"""GitHub collector — trending repos via the Search API.

Searches repos created in the last week, sorted by stars. A token raises the
rate limit but is optional. `stars` is kept as a popularity signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.base import BaseCollector
from app.schemas.article import RawArticle
from app.utils.http import transient_retry
from app.utils.text import clean_text

logger = logging.getLogger(__name__)

_SEARCH = "https://api.github.com/search/repositories"


class GitHubCollector(BaseCollector):
    def __init__(self, *, client: httpx.AsyncClient, token: str = "", limit: int = 25) -> None:
        self.client = client
        self.token = token
        self.limit = limit

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @transient_retry
    async def _search(self, since: str):
        params = {
            "q": f"created:>{since}",
            "sort": "stars",
            "order": "desc",
            "per_page": str(self.limit),
        }
        resp = await self.client.get(_SEARCH, params=params, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def fetch(self) -> list[RawArticle]:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        try:
            data = await self._search(since)
        except Exception:
            logger.exception("GitHub search failed")
            return []

        out: list[RawArticle] = []
        for repo in (data.get("items") or [])[: self.limit]:
            url = repo.get("html_url")
            name = clean_text(repo.get("full_name"))
            if not url or not name:
                continue
            out.append(
                RawArticle(
                    source="github",
                    title=name,
                    url=url,
                    content=clean_text(repo.get("description")),
                    published_at=_iso(repo.get("created_at")),
                    raw_signals={
                        "stars": repo.get("stargazers_count", 0),
                        "language": repo.get("language"),
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
