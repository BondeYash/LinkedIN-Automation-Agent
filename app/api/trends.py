"""Trend routes — run the analyzer and list ranked topics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.analyzers.trend_analyzer import TrendAnalyzer
from app.api.deps import get_article_repo, get_topic_repo, get_trend_repo
from app.repositories.repos import ArticleRepository, TopicRepository, TrendRepository
from app.schemas.trend import TrendOut

router = APIRouter(prefix="/trends", tags=["trends"])


@router.post("/analyze")
async def analyze_trends(
    articles: ArticleRepository = Depends(get_article_repo),
    topics: TopicRepository = Depends(get_topic_repo),
    trends: TrendRepository = Depends(get_trend_repo),
) -> dict:
    """Cluster unprocessed articles into topics and score each. Run after
    collection; the scheduler chains it in Phase 11."""
    analyzer = TrendAnalyzer(articles, topics, trends)
    return (await analyzer.run()).as_dict()


@router.get("", response_model=list[TrendOut])
def list_trends(
    trends: TrendRepository = Depends(get_trend_repo),
    limit: int = Query(default=20, le=100),
) -> list[TrendOut]:
    """Topics ranked by trend score, highest first."""
    return [TrendOut.from_trend(t) for t in trends.ranked(limit=limit)]
