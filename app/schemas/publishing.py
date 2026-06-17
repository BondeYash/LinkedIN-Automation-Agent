"""Publishing DTOs — the result returned by the publish endpoint."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import PostStatus


class PublishResultOut(BaseModel):
    ok: bool
    post_id: int
    status: PostStatus
    linkedin_post_id: str | None = None
    error: str | None = None
    retries: int = 0
