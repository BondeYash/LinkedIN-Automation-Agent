"""FastAPI dependency providers.

Routes ask for the repository they need; these providers build it from a
request-scoped DB session. Keeps routes free of session/repo wiring.

Example:
    @router.get("/news")
    def list_news(articles: ArticleRepository = Depends(get_article_repo)):
        return articles.list()
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_access_token
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.models import User
from app.notifications.service import NotificationService
from app.repositories.repos import (
    AnalyticsRepository,
    ApprovalRepository,
    ArticleRepository,
    AuditLogRepository,
    NotificationRepository,
    PostRepository,
    PublishingRepository,
    SeenHashRepository,
    StyleProfileRepository,
    TopicRepository,
    TrendRepository,
    UserRepository,
)
from app.analyzers.analytics_service import AnalyticsService
from app.analyzers.feedback import FeedbackTuner
from app.analyzers.weekly_report import WeeklyReport
from app.publishers.linkedin_publisher import LinkedInPublisher
from app.services.approval_service import ApprovalService


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


def get_approval_repo(db: Session = Depends(get_db)) -> ApprovalRepository:
    return ApprovalRepository(db)


def get_notification_repo(db: Session = Depends(get_db)) -> NotificationRepository:
    return NotificationRepository(db)


def get_audit_repo(db: Session = Depends(get_db)) -> AuditLogRepository:
    return AuditLogRepository(db)


def get_notification_service(
    notifications: NotificationRepository = Depends(get_notification_repo),
) -> NotificationService:
    return NotificationService(notifications)


def get_approval_service(
    posts: PostRepository = Depends(get_post_repo),
    approvals: ApprovalRepository = Depends(get_approval_repo),
    audit: AuditLogRepository = Depends(get_audit_repo),
    notifier: NotificationService = Depends(get_notification_service),
) -> ApprovalService:
    return ApprovalService(posts, approvals, audit, notifier=notifier)


def get_linkedin_publisher(
    posts: PostRepository = Depends(get_post_repo),
    publishing: PublishingRepository = Depends(get_publishing_repo),
    audit: AuditLogRepository = Depends(get_audit_repo),
) -> LinkedInPublisher:
    return LinkedInPublisher(posts, publishing, audit=audit)


def get_analytics_repo(db: Session = Depends(get_db)) -> AnalyticsRepository:
    return AnalyticsRepository(db)


def get_analytics_service(
    analytics: AnalyticsRepository = Depends(get_analytics_repo),
    publishing: PublishingRepository = Depends(get_publishing_repo),
) -> AnalyticsService:
    return AnalyticsService(analytics, publishing)


def get_weekly_report(
    analytics: AnalyticsRepository = Depends(get_analytics_repo),
    posts: PostRepository = Depends(get_post_repo),
    publishing: PublishingRepository = Depends(get_publishing_repo),
) -> WeeklyReport:
    return WeeklyReport(analytics, posts, publishing)


def get_feedback_tuner(
    posts: PostRepository = Depends(get_post_repo),
) -> FeedbackTuner:
    return FeedbackTuner(posts)


# --- Authentication ----------------------------------------------------------

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    users: UserRepository = Depends(get_user_repo),
) -> User:
    """Resolve the bearer JWT to an active user, or 401."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_access_token(creds.credentials)
        user = users.get(int(claims["sub"]))
    except (TokenError, KeyError, ValueError):
        raise unauthorized
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_role(*roles: UserRole):
    """Dependency factory: allow only the given roles (ADMIN always allowed)."""
    allowed = {UserRole.ADMIN, *roles}

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return _checker
