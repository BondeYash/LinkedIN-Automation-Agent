"""Trend analyzer test — clustering, scoring, and persistence with fakes.

Uses a deterministic keyword embedder (no model download) and in-memory fake
repos so it runs fast and offline. Real DBSCAN does the clustering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from app.analyzers.trend_analyzer import TrendAnalyzer
from app.core.config import get_settings
from app.models.models import Article, Topic, Trend

_KEYWORDS = ("ai", "rust", "startup")


class _KeywordEmbedder:
    """Maps text to a unit vector over a few keywords — same keyword => same
    direction => cosine distance 0 => one cluster."""

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            low = text.lower()
            vec = np.array([float(k in low) for k in _KEYWORDS], dtype=np.float32)
            if not vec.any():
                vec = np.ones(len(_KEYWORDS), dtype=np.float32)
            vec /= np.linalg.norm(vec)
            rows.append(vec)
        return np.vstack(rows)


class _FakeDB:
    def commit(self):
        pass


class _FakeArticleRepo:
    def __init__(self, articles):
        self._articles = articles
        self.db = _FakeDB()

    def unprocessed(self, *, window_hours, limit):
        return [a for a in self._articles if a.processed_at is None][:limit]


class _FakeTopicRepo:
    def __init__(self):
        self.saved = []
        self._next_id = 1

    def create(self, topic, *, commit=False):
        topic.id = self._next_id
        self._next_id += 1
        self.saved.append(topic)
        return topic


class _FakeTrendRepo:
    def __init__(self):
        self.saved = []

    def create(self, trend, *, commit=False):
        self.saved.append(trend)
        return trend


def _article(title, source, signals, hours_old=1):
    when = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    return Article(
        source=source,
        url=f"https://x/{title}".replace(" ", "-"),
        url_hash=title,
        title=title,
        content="",
        raw_signals=signals,
        collected_at=when,
    )


async def test_same_story_clusters_and_scores_rank_correctly():
    get_settings.cache_clear()
    articles = [
        _article("AI breakthrough model", "hackernews", {"score": 500}, hours_old=1),
        _article("New AI model breakthrough", "devto", {"reactions": 50}, hours_old=2),
        _article("Rust release notes", "github", {"stars": 5}, hours_old=40),
    ]
    topic_repo, trend_repo = _FakeTopicRepo(), _FakeTrendRepo()
    analyzer = TrendAnalyzer(
        _FakeArticleRepo(articles),
        topic_repo,
        trend_repo,
        embedder=_KeywordEmbedder(),
    )

    result = await analyzer.run()

    # 3 articles -> 2 topics (two AI stories merge, Rust separate)
    assert result.articles_processed == 3
    assert result.topics_created == 2
    assert len(topic_repo.saved) == 2 and len(trend_repo.saved) == 2

    # every analyzed article is stamped processed
    assert all(a.processed_at is not None for a in articles)

    # the AI topic (popular + fresh) outranks the stale low-engagement Rust topic
    topics_by_id = {t.id: t for t in topic_repo.saved}
    ai_trend = max(trend_repo.saved, key=lambda t: t.score)
    assert "AI" in topics_by_id[ai_trend.topic_id].name
    assert ai_trend.score > min(t.score for t in trend_repo.saved)

    # the merged AI topic has 2 member articles
    ai_topic = topics_by_id[ai_trend.topic_id]
    assert len(ai_topic.articles) == 2
