"""FastAPI dependency providers.

Routes ask for the repository they need; these providers build it from a
request-scoped DB session. Keeps routes free of session/repo wiring.

Example:
    @router.get("/news")
    def list_news(articles: ArticleRepository = Depends(get_article_repo)):
        return articles.list()
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.repos import (
    ArticleRepository,
    PostRepository,
    PublishingRepository,
    SeenHashRepository,
    StyleProfileRepository,
    TopicRepository,
    TrendRepository,
    UserRepository,
)


def get_user_repo(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_article_repo(db: Session = Depends(get_db)) -> ArticleRepository:
    return ArticleRepository(db)


def get_seen_repo(db: Session = Depends(get_db)) -> SeenHashRepository:
    return SeenHashRepository(db)


def get_topic_repo(db: Session = Depends(get_db)) -> TopicRepository:
    return TopicRepository(db)


def get_trend_repo(db: Session = Depends(get_db)) -> TrendRepository:
    return TrendRepository(db)


def get_style_repo(db: Session = Depends(get_db)) -> StyleProfileRepository:
    return StyleProfileRepository(db)


def get_post_repo(db: Session = Depends(get_db)) -> PostRepository:
    return PostRepository(db)


def get_publishing_repo(db: Session = Depends(get_db)) -> PublishingRepository:
    return PublishingRepository(db)
