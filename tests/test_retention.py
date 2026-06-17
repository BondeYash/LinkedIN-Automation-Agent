"""Tests for the seen-hash dedup memory and the retention service."""

from __future__ import annotations

from app.schemas.article import RawArticle
from app.services.collector_service import CollectorService
from app.services.retention_service import PruneResult, RetentionService
from app.utils.text import url_hash


class _FakeDB:
    def commit(self):
        pass


class _FakeArticleRepo:
    def __init__(self):
        self.saved = []
        self.db = _FakeDB()

    def recent_titles(self, *, limit: int = 500):
        return [a.title for a in self.saved]

    def exists_url_hash(self, h: str) -> bool:  # unused when seen_repo present
        return False

    def create(self, article):
        self.saved.append(article)
        return article


class _FakeSeenRepo:
    def __init__(self, preloaded: set[str] | None = None):
        self.hashes = set(preloaded or set())
        self.recorded = []

    def exists(self, h: str) -> bool:
        return h in self.hashes

    def record(self, h: str, source: str | None = None) -> None:
        self.hashes.add(h)
        self.recorded.append(h)


class _StubCollector:
    def __init__(self, items):
        self._items = items

    async def fetch(self):
        return self._items


async def test_seen_hash_blocks_previously_processed_url():
    old_url = "https://x.com/already-known"
    items = [
        RawArticle(source="a", title="Known story", url=old_url),  # in seen memory
        RawArticle(source="b", title="Brand new story", url="https://x.com/new"),
    ]
    seen = _FakeSeenRepo(preloaded={url_hash(old_url)})
    repo = _FakeArticleRepo()
    service = CollectorService(repo, [_StubCollector(items)], seen_repo=seen)

    result = await service.collect()

    assert result.new == 1  # only the brand-new one
    assert result.duplicates == 1  # known url skipped via seen memory
    assert {a.title for a in repo.saved} == {"Brand new story"}
    assert seen.recorded == [url_hash("https://x.com/new")]  # new hash remembered


class _RetentionArticleRepo:
    def __init__(self):
        self.db = _FakeDB()

    def drop_content_older_than(self, days: int) -> int:
        return 5

    def prune_older_than(self, days: int) -> int:
        return 3


class _RetentionSeenRepo:
    def prune_older_than(self, days: int) -> int:
        return 7


def test_retention_service_aggregates_counts():
    result = RetentionService(
        _RetentionArticleRepo(), _RetentionSeenRepo()
    ).run()

    assert isinstance(result, PruneResult)
    assert result.as_dict() == {
        "content_dropped": 5,
        "articles_deleted": 3,
        "hashes_pruned": 7,
    }
