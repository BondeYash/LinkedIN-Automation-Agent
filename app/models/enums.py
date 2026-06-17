"""Enumerations used by the ORM models.

Stored as their string `value` in the database (native ENUM on PostgreSQL,
VARCHAR on SQLite test DBs).
"""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class PostStatus(str, enum.Enum):
    """Lifecycle of a generated post (see Phase 7 approval flow)."""

    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    REGENERATE = "regenerate"
    NEEDS_REVIEW = "needs_review"  # quality gate (Phase 6) flagged it for a human
    PUBLISHED = "published"
    FAILED = "failed"


class ApprovalAction(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    REGENERATE = "regenerate"


class PublishStatus(str, enum.Enum):
    PUBLISHED = "published"
    FAILED = "failed"


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    TEAMS = "teams"
    SHEETS = "sheets"
    LOG = "log"  # offline fallback channel (Phase 7)


class NotificationStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"


class PostSource(str, enum.Enum):
    """Provenance of an account post (Phase 10 coach)."""

    APP = "app"
    MANUAL = "manual"
