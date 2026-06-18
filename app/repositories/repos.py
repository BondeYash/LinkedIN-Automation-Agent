"""Concrete repositories — one per table we read/write often.

Each adds the domain queries its callers need on top of `BaseRepository` CRUD.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import joinedload

from app.models.enums import PostStatus, PublishStatus
from app.models.models import (
    Analytics,
    Approval,
    Article,
    AuditLog,
    GeneratedPost,
    Notification,
    PublishingHistory,
    SeenHash,
    StyleProfile,
    Topic,
    Trend,
    User,
)
from app.repositories.base import BaseRepository


def _utc_cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


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

    def recent_titles(self, *, limit: int = 500) -> list[str]:
        """Recent article titles — used for fuzzy near-duplicate detection."""
        stmt = (
            select(Article.title)
            .order_by(Article.collected_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count(self) -> int:
        return int(self.db.execute(select(func.count(Article.id))).scalar_one())

    def unprocessed(self, *, window_hours: int = 72, limit: int = 500) -> list[Article]:
        """Articles collected within `window_hours` that the trend analyzer has
        not clustered yet (`processed_at IS NULL`), newest first."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        stmt = (
            select(Article)
            .where(Article.processed_at.is_(None), Article.collected_at >= cutoff)
            .order_by(Article.collected_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def prune_older_than(self, days: int) -> int:
        """Delete article rows older than `days`. Returns rows removed."""
        stmt = delete(Article).where(Article.collected_at < _utc_cutoff(days))
        result = self.db.execute(stmt)
        return result.rowcount or 0

    def drop_content_older_than(self, days: int) -> int:
        """Null the heavy `content` text on articles older than `days` (keeps the
        cheap metadata row). Returns rows updated."""
        stmt = (
            update(Article)
            .where(Article.collected_at < _utc_cutoff(days), Article.content.is_not(None))
            .values(content=None)
        )
        result = self.db.execute(stmt)
        return result.rowcount or 0


class TopicRepository(BaseRepository[Topic]):
    model = Topic


class TrendRepository(BaseRepository[Trend]):
    model = Trend

    def top_recent(self, *, limit: int = 10) -> list[Trend]:
        stmt = select(Trend).order_by(Trend.run_date.desc(), Trend.score.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def ranked(self, *, limit: int = 20) -> list[Trend]:
        """Latest trends, highest score first, with the topic eager-loaded for
        the API response (avoids lazy-load after the session closes)."""
        stmt = (
            select(Trend)
            .options(joinedload(Trend.topic))
            .order_by(Trend.run_date.desc(), Trend.score.desc())
            .limit(limit)
        )
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

    # Statuses that still need a human decision (the approval queue).
    REVIEW_STATUSES = (
        PostStatus.DRAFT,
        PostStatus.NEEDS_REVIEW,
        PostStatus.PENDING,
        PostStatus.EDITED,
    )

    def review_queue(self, *, limit: int = 100) -> list[GeneratedPost]:
        """Drafts awaiting approval, with topic eager-loaded for the dashboard."""
        stmt = (
            select(GeneratedPost)
            .where(GeneratedPost.status.in_(self.REVIEW_STATUSES))
            .options(joinedload(GeneratedPost.topic))
            .order_by(GeneratedPost.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())


class SeenHashRepository(BaseRepository[SeenHash]):
    """Dedup-memory store. Survives article pruning so old news is never
    re-ingested."""

    model = SeenHash

    def exists(self, url_hash: str) -> bool:
        return self.db.get(SeenHash, url_hash) is not None

    def record(self, url_hash: str, source: str | None = None) -> None:
        """Insert the hash, or bump `last_seen` if already present."""
        existing = self.db.get(SeenHash, url_hash)
        now = datetime.now(timezone.utc)
        if existing is None:
            self.db.add(SeenHash(url_hash=url_hash, source=source, last_seen=now))
        else:
            existing.last_seen = now

    def prune_older_than(self, days: int) -> int:
        """Drop hashes not seen within `days`. Returns rows removed."""
        stmt = delete(SeenHash).where(SeenHash.last_seen < _utc_cutoff(days))
        result = self.db.execute(stmt)
        return result.rowcount or 0


class ApprovalRepository(BaseRepository[Approval]):
    model = Approval

    def for_post(self, post_id: int) -> list[Approval]:
        stmt = (
            select(Approval)
            .where(Approval.post_id == post_id)
            .order_by(Approval.decided_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())


class NotificationRepository(BaseRepository[Notification]):
    model = Notification


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def record(
        self, *, actor: str | None, action: str, entity: str | None, payload: dict | None = None
    ) -> AuditLog:
        row = AuditLog(actor=actor, action=action, entity=entity, payload=payload)
        self.db.add(row)
        self.db.flush()
        return row


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

    def published_post_ids(self) -> dict[int, str]:
        """Map each post_id that was successfully published to its (latest)
        LinkedIn share urn — the key the analytics client needs to pull metrics."""
        stmt = (
            select(PublishingHistory.post_id, PublishingHistory.linkedin_post_id)
            .where(
                PublishingHistory.status == PublishStatus.PUBLISHED,
                PublishingHistory.linkedin_post_id.is_not(None),
            )
            .order_by(PublishingHistory.id.asc())  # later rows overwrite -> latest wins
        )
        return {pid: urn for pid, urn in self.db.execute(stmt).all()}


class AnalyticsRepository(BaseRepository[Analytics]):
    """Append-only engagement time-series. Each sync inserts a new row stamped
    with `captured_at`; rows are never overwritten so trends stay visible."""

    model = Analytics

    def add(
        self, post_id: int, *, likes: int, comments: int, shares: int, impressions: int
    ) -> Analytics:
        row = Analytics(
            post_id=post_id,
            likes=likes,
            comments=comments,
            shares=shares,
            impressions=impressions,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def series_for_post(self, post_id: int) -> list[Analytics]:
        """Full capture history for one post, oldest first."""
        stmt = (
            select(Analytics)
            .where(Analytics.post_id == post_id)
            .order_by(Analytics.captured_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def latest_per_post(self) -> list[Analytics]:
        """The most recent capture for every post (one row per post)."""
        sub = (
            select(Analytics.post_id, func.max(Analytics.id).label("max_id"))
            .group_by(Analytics.post_id)
            .subquery()
        )
        stmt = select(Analytics).join(sub, Analytics.id == sub.c.max_id)
        return list(self.db.execute(stmt).scalars().all())

    def since(self, *, days: int) -> list[Analytics]:
        """All captures within the last `days`, oldest first (report window)."""
        cutoff = _utc_cutoff(days)
        stmt = (
            select(Analytics)
            .where(Analytics.captured_at >= cutoff)
            .order_by(Analytics.captured_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
