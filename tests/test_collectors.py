"""Collector unit tests — fully mocked HTTP, no real network.

Each HTTP collector gets an httpx.AsyncClient backed by a MockTransport that
returns canned payloads, so we test parsing/normalization deterministically.
The service dedup logic is tested against a fake in-memory repository.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.collectors.devto_collector import DevToCollector
from app.collectors.github_collector import GitHubCollector
from app.collectors.hackernews_collector import HackerNewsCollector
from app.collectors.rss_collector import RSSCollector
from app.schemas.article import RawArticle
from app.services.collector_service import CollectorService

SAMPLE_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Demo</title>
  <item>
    <title>Big AI breakthrough announced</title>
    <link>https://example.com/ai-breakthrough</link>
    <description>Summary here</description>
    <pubDate>Tue, 10 Jun 2025 09:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Second story</title>
    <link>https://example.com/second</link>
    <description>More</description>
  </item>
</channel></rss>"""


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_rss_collector_parses_feed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SAMPLE_RSS)

    async with _client(handler) as client:
        collector = RSSCollector(
            "https://example.com/feed", source_name="Demo", client=client
        )
        items = await collector.fetch()

    assert len(items) == 2
    assert items[0].source == "Demo"
    assert items[0].url == "https://example.com/ai-breakthrough"
    assert items[0].published_at is not None


async def test_hackernews_collector_parses_stories():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "topstories" in url:
            return httpx.Response(200, json=[101, 102])
        if "/item/101" in url:
            return httpx.Response(
                200,
                json={
                    "type": "story",
                    "title": "HN story one",
                    "url": "https://example.com/hn1",
                    "score": 250,
                    "descendants": 40,
                    "time": 1718000000,
                },
            )
        return httpx.Response(
            200,
            json={"type": "story", "title": "Ask HN: anything?", "score": 12, "time": 1718000001},
        )

    async with _client(handler) as client:
        items = await HackerNewsCollector(client=client, limit=2).fetch()

    assert len(items) == 2
    by_title = {i.title: i for i in items}
    assert by_title["HN story one"].raw_signals["score"] == 250
    # Ask HN with no url falls back to the discussion link.
    assert "news.ycombinator.com/item?id=102" in by_title["Ask HN: anything?"].url


async def test_github_collector_parses_repos():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "full_name": "octocat/cool",
                        "html_url": "https://github.com/octocat/cool",
                        "description": "A cool repo",
                        "stargazers_count": 999,
                        "language": "Python",
                        "created_at": "2025-06-10T00:00:00Z",
                    }
                ]
            },
        )

    async with _client(handler) as client:
        items = await GitHubCollector(client=client, token="x").fetch()

    assert len(items) == 1
    assert items[0].source == "github"
    assert items[0].raw_signals["stars"] == 999


async def test_devto_collector_parses_articles():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "title": "Dev.to top post",
                    "url": "https://dev.to/x/post",
                    "description": "desc",
                    "positive_reactions_count": 120,
                    "comments_count": 8,
                    "tag_list": ["python"],
                    "published_at": "2025-06-10T00:00:00Z",
                }
            ],
        )

    async with _client(handler) as client:
        items = await DevToCollector(client=client).fetch()

    assert len(items) == 1
    assert items[0].raw_signals["reactions"] == 120


async def test_rss_collector_survives_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handler) as client:
        items = await RSSCollector(
            "https://example.com/feed", source_name="Demo", client=client
        ).fetch()

    assert items == []  # error swallowed, returns empty not raises


# --- Service dedup ----------------------------------------------------------


class _FakeArticleRepo:
    """In-memory stand-in for ArticleRepository."""

    def __init__(self):
        self.saved = []
        self._hashes = set()

        class _DB:
            def commit(self_inner):
                pass

        self.db = _DB()

    def recent_titles(self, *, limit: int = 500):
        return [a.title for a in self.saved]

    def exists_url_hash(self, url_hash: str) -> bool:
        return url_hash in self._hashes

    def create(self, article):
        self.saved.append(article)
        self._hashes.add(article.url_hash)
        return article


class _StubCollector:
    def __init__(self, items):
        self._items = items

    async def fetch(self):
        return self._items


class _BrokenCollector:
    async def fetch(self):
        raise RuntimeError("source down")


async def test_service_dedups_url_and_fuzzy_title_and_isolates_failures():
    items = [
        RawArticle(source="a", title="Quantum computing leaps forward", url="https://x.com/q"),
        # exact-url duplicate
        RawArticle(source="b", title="Different headline entirely", url="https://x.com/q"),
        # fuzzy-title near-duplicate of the first
        RawArticle(source="c", title="Quantum computing leaps forward!!!", url="https://x.com/q2"),
        # genuinely new
        RawArticle(source="d", title="Rust adoption keeps climbing", url="https://x.com/rust"),
    ]
    repo = _FakeArticleRepo()
    service = CollectorService(
        repo,
        [_StubCollector(items), _BrokenCollector()],
        title_threshold=90,
    )

    result = await service.collect()

    assert result.collected == 4
    assert result.new == 2  # first + rust
    assert result.duplicates == 2  # url dup + fuzzy dup
    assert len(result.errors) == 1  # broken collector isolated
    saved_titles = {a.title for a in repo.saved}
    assert saved_titles == {"Quantum computing leaps forward", "Rust adoption keeps climbing"}
