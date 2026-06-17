"""Approval DTOs — request bodies and the dashboard card view."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PostStatus
from app.models.models import GeneratedPost


class DecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class EditRequest(BaseModel):
    headline: str | None = None
    hook: str | None = None
    body: str | None = None
    cta: str | None = None
    hashtags: list[str] | None = None
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalCard(BaseModel):
    """One pending draft as shown in the approval queue / dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str | None = None
    trend_score: float | None
    headline: str | None
    hook: str | None
    body: str
    cta: str | None
    hashtags: list
    review_notes: dict | None
    status: PostStatus
    created_at: datetime

    @classmethod
    def from_post(cls, post: GeneratedPost) -> "ApprovalCard":
        return cls(
            id=post.id,
            topic=post.topic.name if post.topic else None,
            trend_score=post.trend_score,
            headline=post.headline,
            hook=post.hook,
            body=post.body,
            cta=post.cta,
            hashtags=post.hashtags or [],
            review_notes=post.review_notes,
            status=post.status,
            created_at=post.created_at,
        )
