"""DTOs for generated posts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PostStatus


class GenerateRequest(BaseModel):
    topic_id: int
    style_name: str = Field(default="default", max_length=255)


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int | None
    style_id: int | None
    headline: str | None
    hook: str | None
    body: str
    cta: str | None
    hashtags: list
    reason: str | None
    trend_score: float | None
    status: PostStatus
    created_at: datetime
