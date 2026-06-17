"""ORM models — every table in the system.

SQLAlchemy 2.0 typed style (`Mapped` / `mapped_column`). All tables are defined
now (even ones used by later phases) so the schema is migrated once. Types stay
portable (JSON, generic Enum) so a SQLite test DB and PostgreSQL both work.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.enums import (
    ApprovalAction,
    NotificationChannel,
    NotificationStatus,
    PostSource,
    PostStatus,
    PublishStatus,
    UserRole,
)

# Convenience: a column tracking row creation, server-stamped.
_created = lambda: mapped_column(  # noqa: E731
    DateTime(timezone=True), server_default=func.now(), nullable=False
)


# --- Association: articles <-> topics (many-to-many) ------------------------
article_topics = Table(
    "article_topics",
    Base.metadata,
    Column("article_id", ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_pw: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created()

    approvals: Mapped[list["Approval"]] = relationship(back_populates="user")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Source-specific popularity signals (HN score, GitHub stars, ...). Tiny JSON,
    # kept even after `content` is dropped — the trend analyzer (Phase 3) reads it.
    raw_signals: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Set by the trend analyzer (Phase 3); drives content-dropping + prune order.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topics: Mapped[list["Topic"]] = relationship(
        secondary=article_topics, back_populates="articles"
    )


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cluster_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    created_at: Mapped[datetime] = _created()

    articles: Mapped[list["Article"]] = relationship(
        secondary=article_topics, back_populates="topics"
    )
    trends: Mapped[list["Trend"]] = relationship(back_populates="topic")
    posts: Mapped[list["GeneratedPost"]] = relationship(back_populates="topic")


class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    popularity: Mapped[float] = mapped_column(Float, default=0.0)
    recency: Mapped[float] = mapped_column(Float, default=0.0)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    run_date: Mapped[datetime] = _created()

    topic: Mapped["Topic"] = relationship(back_populates="trends")


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = _created()

    posts: Mapped[list["GeneratedPost"]] = relationship(back_populates="style")


class GeneratedPost(Base):
    __tablename__ = "generated_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True, nullable=True
    )
    style_id: Mapped[int | None] = mapped_column(
        ForeignKey("style_profiles.id", ondelete="SET NULL"), nullable=True
    )
    headline: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hook: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    best_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus), default=PostStatus.DRAFT, nullable=False, index=True
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    topic: Mapped["Topic"] = relationship(back_populates="posts")
    style: Mapped["StyleProfile"] = relationship(back_populates="posts")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="post")
    publishing: Mapped[list["PublishingHistory"]] = relationship(back_populates="post")
    analytics: Mapped[list["Analytics"]] = relationship(back_populates="post")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="post")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[ApprovalAction] = mapped_column(Enum(ApprovalAction), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = _created()

    post: Mapped["GeneratedPost"] = relationship(back_populates="approvals")
    user: Mapped["User"] = relationship(back_populates="approvals")


class PublishingHistory(Base):
    __tablename__ = "publishing_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="CASCADE"), index=True
    )
    linkedin_post_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    status: Mapped[PublishStatus] = mapped_column(Enum(PublishStatus), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    post: Mapped["GeneratedPost"] = relationship(back_populates="publishing")


class Analytics(Base):
    __tablename__ = "analytics"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="CASCADE"), index=True
    )
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    captured_at: Mapped[datetime] = _created()

    post: Mapped["GeneratedPost"] = relationship(back_populates="analytics")


class Embedding(Base):
    __tablename__ = "embeddings"
    __table_args__ = (UniqueConstraint("ref_type", "ref_id", name="uq_embedding_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_type: Mapped[str] = mapped_column(String(50), nullable=False)  # article | post
    ref_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Chroma id
    created_at: Mapped[datetime] = _created()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(Enum(NotificationChannel), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(Enum(NotificationStatus), nullable=False)
    sent_at: Mapped[datetime] = _created()

    post: Mapped["GeneratedPost"] = relationship(back_populates="notifications")


class AccountPost(Base):
    """A post pulled from your own LinkedIn account (Phase 10 coach)."""

    __tablename__ = "account_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    linkedin_post_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    length: Mapped[int] = mapped_column(Integer, default=0)
    hashtag_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[PostSource] = mapped_column(Enum(PostSource), nullable=False)
    eng_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = _created()

    tips: Mapped[list["ImprovementTip"]] = relationship(back_populates="account_post")


class EngagementInsight(Base):
    __tablename__ = "engagement_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric: Mapped[str] = mapped_column(String(255), nullable=False)
    finding: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = _created()


class ImprovementTip(Base):
    __tablename__ = "improvement_tips"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_posts.id", ondelete="CASCADE"), index=True, nullable=True
    )
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    expected_lift: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = _created()

    account_post: Mapped["AccountPost"] = relationship(back_populates="tips")


class SeenHash(Base):
    """Lightweight dedup memory that outlives pruned articles.

    Holds only a url hash + timestamps (~70 bytes/row), kept ~60 days. Lets the
    collector skip a story it already processed even after the raw `articles`
    row has been pruned, so old news is never re-ingested.
    """

    __tablename__ = "seen_hashes"

    url_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[datetime] = _created()
