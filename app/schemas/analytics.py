"""Analytics DTOs — sync result + the weekly report response."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SyncResultOut(BaseModel):
    synced: int
    skipped: int
    errors: int


class AnalyticsOut(BaseModel):
    """Current standing + weekly report. The report sections are open dicts so the
    pandas-built payload passes through without a rigid schema per section."""

    report: dict[str, Any]
    feedback_applied: bool = False
