"""DTOs for collected articles."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RawArticle(BaseModel):
    """One normalized item from any source, before it becomes an `Article` row.

    `raw_signals` carries source-specific extras (e.g. HN/Reddit `score`,
    GitHub `stars`) that the trend analyzer (Phase 3) later consumes.
    """

    source: str
    title: str
    url: str
    content: str | None = None
    published_at: datetime | None = None
    raw_signals: dict = Field(default_factory=dict)


class ArticleOut(BaseModel):
    """Article response shape for the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    title: str
    url: str
    published_at: datetime | None
    collected_at: datetime
