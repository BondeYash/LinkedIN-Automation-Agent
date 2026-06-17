"""DTOs for style-profile endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StyleAnalyzeRequest(BaseModel):
    """Build/refresh a named style profile.

    If `posts` is omitted, the analyzer falls back to the seed reference posts.
    """

    name: str = Field(default="default", max_length=255)
    source: str | None = Field(default=None, max_length=255)
    posts: list[str] = Field(default_factory=list)


class StyleProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str | None
    features: dict
    created_at: datetime
