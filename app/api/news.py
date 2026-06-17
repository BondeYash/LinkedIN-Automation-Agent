"""News routes — trigger collection and list stored articles."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import get_article_repo
from app.core.config import get_settings
from app.models.models import Article
from app.repositories.repos import ArticleRepository
from app.schemas.article import ArticleOut
from app.services.collector_service import CollectorService, build_default_collectors

router = APIRouter(prefix="/news", tags=["news"])


@router.post("/collect")
async def collect_news(articles: ArticleRepository = Depends(get_article_repo)) -> dict:
    """Run every collector once, dedup, and store new articles."""
    settings = get_settings()
    timeout = httpx.Timeout(settings.collector_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "linkedin-agent/0.1"}) as client:
        collectors = build_default_collectors(client, settings)
        service = CollectorService(
            articles,
            collectors,
            max_concurrency=settings.collector_max_concurrency,
            title_threshold=settings.dedup_title_threshold,
        )
        result = await service.collect()
    return result.as_dict()


@router.get("", response_model=list[ArticleOut])
def list_news(
    articles: ArticleRepository = Depends(get_article_repo),
    source: str | None = Query(default=None, description="Filter by source"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Article]:
    """List stored articles, newest first, optionally filtered by source."""
    stmt = select(Article).order_by(Article.collected_at.desc())
    if source:
        stmt = stmt.where(Article.source == source)
    stmt = stmt.limit(limit).offset(offset)
    return list(articles.db.execute(stmt).scalars().all())
