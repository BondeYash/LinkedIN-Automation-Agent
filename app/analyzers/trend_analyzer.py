"""Trend analyzer — cluster recent articles into topics and score each topic.

Pipeline (one run):
  1. pull unprocessed articles inside the analysis window,
  2. embed `title + content` into meaning-vectors,
  3. DBSCAN (cosine) groups articles about the same story into one topic,
  4. score each topic = popularity + recency + relevance (normalized 0–1),
  5. persist Topic + Trend rows, link member articles, stamp `processed_at`.

Scoring math lives in `scoring.py` (pure, unit-tested); this module does the
I/O and the embedding/clustering orchestration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from app.ai.embeddings import Embedder, embed_async, get_embedder
from app.analyzers import scoring
from app.core.config import Settings, get_settings
from app.models.models import Article, Topic, Trend
from app.repositories.repos import ArticleRepository, TopicRepository, TrendRepository

logger = logging.getLogger(__name__)


@dataclass
class AnalyzeResult:
    articles_processed: int = 0
    topics_created: int = 0

    def as_dict(self) -> dict:
        return {
            "articles_processed": self.articles_processed,
            "topics_created": self.topics_created,
        }


@dataclass
class _ScoredTopic:
    cluster_id: int
    articles: list[Article]
    name: str
    raw_popularity: float
    recency: float
    relevance: float


class TrendAnalyzer:
    def __init__(
        self,
        article_repo: ArticleRepository,
        topic_repo: TopicRepository,
        trend_repo: TrendRepository,
        *,
        embedder: Embedder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.article_repo = article_repo
        self.topic_repo = topic_repo
        self.trend_repo = trend_repo
        self.settings = settings or get_settings()
        self.embedder = embedder or get_embedder()

    async def run(self) -> AnalyzeResult:
        s = self.settings
        articles = self.article_repo.unprocessed(
            window_hours=s.analyze_window_hours, limit=s.analyze_max_articles
        )
        if not articles:
            logger.info("Trend analysis: no unprocessed articles")
            return AnalyzeResult()

        vectors = await embed_async(self.embedder, [self._text(a) for a in articles])
        theme_vectors = await embed_async(
            self.embedder, [t.strip() for t in s.trend_themes.split(";") if t.strip()]
        )

        labels = self._cluster(vectors)
        scored = self._score_clusters(articles, vectors, labels, theme_vectors)
        self._persist(scored)

        logger.info(
            "Trend analysis: processed=%d topics=%d", len(articles), len(scored)
        )
        return AnalyzeResult(articles_processed=len(articles), topics_created=len(scored))

    # --- internals -----------------------------------------------------------

    @staticmethod
    def _text(article: Article) -> str:
        body = (article.content or "")[:500]
        return f"{article.title}. {body}".strip()

    def _cluster(self, vectors: np.ndarray) -> np.ndarray:
        """DBSCAN over cosine distance. min_samples=1 → no noise: a unique
        article forms its own single-member topic."""
        from sklearn.cluster import DBSCAN

        if len(vectors) == 1:
            return np.array([0])
        labels = DBSCAN(
            eps=self.settings.cluster_eps,
            min_samples=self.settings.cluster_min_samples,
            metric="cosine",
        ).fit_predict(vectors)
        return labels

    def _score_clusters(
        self,
        articles: list[Article],
        vectors: np.ndarray,
        labels: np.ndarray,
        theme_vectors: np.ndarray,
    ) -> list[_ScoredTopic]:
        now = datetime.now(timezone.utc)
        half_life = self.settings.recency_half_life_hours

        groups: dict[int, list[int]] = {}
        for idx, label in enumerate(labels):
            groups.setdefault(int(label), []).append(idx)

        scored: list[_ScoredTopic] = []
        for cluster_id, idxs in groups.items():
            members = [articles[i] for i in idxs]

            total_engagement = sum(scoring.engagement_of(a.raw_signals) for a in members)
            source_count = len({a.source for a in members})
            raw_pop = scoring.raw_popularity(total_engagement, source_count)

            freshest_hours = min(self._hours_old(a, now) for a in members)
            recency = scoring.recency(freshest_hours, half_life)

            topic_vec = vectors[idxs].mean(axis=0)
            relevance = self._relevance(topic_vec, theme_vectors)

            # Representative title = the highest-engagement member.
            name = max(members, key=lambda a: scoring.engagement_of(a.raw_signals)).title

            scored.append(
                _ScoredTopic(
                    cluster_id=cluster_id,
                    articles=members,
                    name=name[:255],
                    raw_popularity=raw_pop,
                    recency=recency,
                    relevance=relevance,
                )
            )
        return scored

    @staticmethod
    def _hours_old(article: Article, now: datetime) -> float:
        ref = article.published_at or article.collected_at
        if ref is None:
            return 0.0
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ref).total_seconds() / 3600.0)

    @staticmethod
    def _relevance(topic_vec: np.ndarray, theme_vectors: np.ndarray) -> float:
        """Max cosine similarity between the topic and any reference theme.
        Vectors are already L2-normalized, so dot product = cosine."""
        if theme_vectors.size == 0:
            return 0.0
        norm = np.linalg.norm(topic_vec)
        if norm > 0:
            topic_vec = topic_vec / norm
        sims = theme_vectors @ topic_vec
        return scoring.clamp01(float(sims.max()))

    def _persist(self, scored: list[_ScoredTopic]) -> None:
        weights = scoring.ScoreWeights(
            popularity=self.settings.weight_popularity,
            recency=self.settings.weight_recency,
            relevance=self.settings.weight_relevance,
        )
        normalized_pop = scoring.normalize([t.raw_popularity for t in scored])
        now = datetime.now(timezone.utc)

        for topic_data, popularity in zip(scored, normalized_pop):
            topic = Topic(name=topic_data.name, cluster_id=topic_data.cluster_id)
            topic.articles = topic_data.articles
            self.topic_repo.create(topic)

            score = scoring.combine(
                popularity, topic_data.recency, topic_data.relevance, weights
            )
            self.trend_repo.create(
                Trend(
                    topic_id=topic.id,
                    score=score,
                    popularity=popularity,
                    recency=topic_data.recency,
                    relevance=topic_data.relevance,
                )
            )
            for article in topic_data.articles:
                article.processed_at = now

        self.article_repo.db.commit()
