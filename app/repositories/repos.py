"""Concrete repositories — one per table we read/write often.

Each adds the domain queries its callers need on top of `BaseRepository` CRUD.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.enums import PostStatus
from app.models.models import (
    Article,
    GeneratedPost,
    PublishingHistory,
    StyleProfile,
    Topic,
    Trend,
    User,
)
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()


class ArticleRepository(BaseRepository[Article]):
    model = Article

    def get_by_url_hash(self, url_hash: str) -> Article | None:
        stmt = select(Article).where(Article.url_hash == url_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def exists_url_hash(self, url_hash: str) -> bool:
        return self.get_by_url_hash(url_hash) is not None


class TopicRepository(BaseRepository[Topic]):
    model = Topic


class TrendRepository(BaseRepository[Trend]):
    model = Trend

    def top_recent(self, *, limit: int = 10) -> list[Trend]:
        stmt = select(Trend).order_by(Trend.run_date.desc(), Trend.score.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())


class StyleProfileRepository(BaseRepository[StyleProfile]):
    model = StyleProfile

    def get_by_name(self, name: str) -> StyleProfile | None:
        stmt = select(StyleProfile).where(StyleProfile.name == name)
        return self.db.execute(stmt).scalar_one_or_none()


class PostRepository(BaseRepository[GeneratedPost]):
    model = GeneratedPost

    def by_status(self, status: PostStatus, *, limit: int = 100) -> list[GeneratedPost]:
        stmt = (
            select(GeneratedPost)
            .where(GeneratedPost.status == status)
            .order_by(GeneratedPost.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_pending(self, *, limit: int = 100) -> list[GeneratedPost]:
        return self.by_status(PostStatus.PENDING, limit=limit)


class PublishingRepository(BaseRepository[PublishingHistory]):
    model = PublishingHistory

    def latest_for_post(self, post_id: int) -> PublishingHistory | None:
        stmt = (
            select(PublishingHistory)
            .where(PublishingHistory.post_id == post_id)
            .order_by(PublishingHistory.id.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()
