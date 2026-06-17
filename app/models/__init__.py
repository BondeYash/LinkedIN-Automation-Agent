"""ORM models package.

Re-export every model and enum so callers can `from app.models import User` and
so Alembic's autogenerate sees all tables via `Base.metadata`.
"""

from app.models.enums import (
    ApprovalAction,
    NotificationChannel,
    NotificationStatus,
    PostSource,
    PostStatus,
    PublishStatus,
    UserRole,
)
from app.models.models import (
    AccountPost,
    Analytics,
    Approval,
    Article,
    AuditLog,
    Embedding,
    EngagementInsight,
    GeneratedPost,
    ImprovementTip,
    Notification,
    PublishingHistory,
    SeenHash,
    StyleProfile,
    Topic,
    Trend,
    User,
    article_topics,
)

__all__ = [
    "AccountPost",
    "Analytics",
    "Approval",
    "Article",
    "AuditLog",
    "Embedding",
    "EngagementInsight",
    "GeneratedPost",
    "ImprovementTip",
    "Notification",
    "PublishingHistory",
    "SeenHash",
    "StyleProfile",
    "Topic",
    "Trend",
    "User",
    "article_topics",
    "ApprovalAction",
    "NotificationChannel",
    "NotificationStatus",
    "PostSource",
    "PostStatus",
    "PublishStatus",
    "UserRole",
]
