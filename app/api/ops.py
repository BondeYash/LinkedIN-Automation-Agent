"""Ops routes — trigger the scheduled jobs on demand (Phase 11).

The daily pipeline and weekly report normally fire on the APScheduler cron, but
these endpoints let an admin run them immediately (smoke tests, a forced catch-up
run, or a manual "do it now"). Same code path as the scheduler — they call the
exact job bodies.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.models.enums import UserRole
from app.models.models import User
from app.scheduler.scheduler import run_daily_pipeline, run_weekly_report

router = APIRouter(prefix="/ops", tags=["ops"])

_admin = require_role(UserRole.ADMIN)


@router.post("/run-daily")
async def run_daily(user: User = Depends(_admin)) -> dict:
    """Run the full daily pipeline now: collect → analyze → generate top-N →
    submit (which notifies you on WhatsApp with approve links)."""
    return await run_daily_pipeline()


@router.post("/weekly-report")
async def weekly_report(user: User = Depends(_admin)) -> dict:
    """Run the weekly analytics sync + WhatsApp report now."""
    return await run_weekly_report()
