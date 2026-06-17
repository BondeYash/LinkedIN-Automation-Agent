"""DTOs for trends/topics returned by the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TrendOut(BaseModel):
    """A ranked topic with its score breakdown."""

    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    topic: str
    score: float
    popularity: float
    recency: float
    relevance: float
    run_date: datetime

    @classmethod
    def from_trend(cls, trend) -> "TrendOut":
        return cls(
            topic_id=trend.topic_id,
            topic=trend.topic.name if trend.topic else "",
            score=trend.score,
            popularity=trend.popularity,
            recency=trend.recency,
            relevance=trend.relevance,
            run_date=trend.run_date,
        )
