"""Analytics routes — the measure-and-improve end of the pipeline.

- `GET  /analytics`       → current weekly report (top posts, WoW delta, best
  topics/hashtags/hours). Read access for any authenticated user.
- `POST /analytics/sync`  → pull fresh metrics for every published post (append
  to the time-series), rebuild the report, and feed the winning patterns back
  into the generator's optimization hints. Editor/admin only; also driven by the
  scheduler in Phase 11.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_analytics_service,
    get_current_user,
    get_feedback_tuner,
    get_weekly_report,
    require_role,
)
from app.analyzers.analytics_service import AnalyticsService
from app.analyzers.feedback import FeedbackTuner
from app.analyzers.weekly_report import WeeklyReport
from app.models.enums import UserRole
from app.models.models import User
from app.schemas.analytics import AnalyticsOut, SyncResultOut

router = APIRouter(prefix="/analytics", tags=["analytics"])

_editor = require_role(UserRole.EDITOR)


@router.get("", response_model=AnalyticsOut)
async def get_analytics(
    report: WeeklyReport = Depends(get_weekly_report),
    user: User = Depends(get_current_user),
) -> AnalyticsOut:
    return AnalyticsOut(report=report.build())


@router.post("/sync", response_model=SyncResultOut)
async def sync_analytics(
    service: AnalyticsService = Depends(get_analytics_service),
    report: WeeklyReport = Depends(get_weekly_report),
    feedback: FeedbackTuner = Depends(get_feedback_tuner),
    user: User = Depends(_editor),
) -> SyncResultOut:
    result = await service.sync()
    # Rebuild the report on fresh data and push winning patterns into the prompt.
    feedback.run(report.build())
    return SyncResultOut(synced=result.synced, skipped=result.skipped, errors=result.errors)
