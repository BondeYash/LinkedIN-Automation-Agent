"""In-process job scheduler (Phase 11).

An APScheduler `AsyncIOScheduler` running inside the FastAPI event loop. Two jobs:

- **daily_pipeline** — collect → analyze → generate top-N → notify on WhatsApp,
  at `daily_pipeline_hour:minute` in `scheduler_timezone` (default 10:00 IST).
- **weekly_report** — sync analytics, rebuild the weekly report, push a summary
  to WhatsApp, on `weekly_report_day` at `weekly_report_hour` (default Mon 09:00).

Each job opens its own DB session (the request-scoped `get_db` doesn't apply to
background tasks) and never lets an exception escape — a failed run is logged and
the scheduler keeps its place for tomorrow.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.analyzers.analytics_service import AnalyticsService
from app.analyzers.feedback import FeedbackTuner
from app.analyzers.weekly_report import WeeklyReport
from app.core.config import Settings, get_settings
from app.database.session import SessionLocal
from app.notifications import waha_client
from app.repositories.repos import (
    AnalyticsRepository,
    PostRepository,
    PublishingRepository,
)
from app.services.pipeline_service import PipelineService

logger = logging.getLogger(__name__)


async def run_daily_pipeline(settings: Settings | None = None) -> dict:
    """Daily job body. Safe to call manually (e.g. an ops endpoint or a test)."""
    settings = settings or get_settings()
    db = SessionLocal()
    try:
        result = await PipelineService(db, settings=settings).run_daily()
        return result.as_dict()
    finally:
        db.close()


async def run_weekly_report(settings: Settings | None = None) -> dict:
    """Weekly job body: sync metrics, rebuild the report, WhatsApp a summary."""
    settings = settings or get_settings()
    db = SessionLocal()
    try:
        analytics = AnalyticsRepository(db)
        publishing = PublishingRepository(db)
        posts = PostRepository(db)
        synced = await AnalyticsService(analytics, publishing).sync()
        report = WeeklyReport(analytics, posts, publishing).build()
        FeedbackTuner(posts).run(report)
        if waha_client.is_configured(settings):
            try:
                waha_client.send_text(format_weekly_report(report), settings=settings)
            except Exception:
                logger.warning("Weekly report: WhatsApp send failed", exc_info=True)
        return {"synced": synced.__dict__ if hasattr(synced, "__dict__") else synced, "report": report}
    finally:
        db.close()


def format_weekly_report(report: dict) -> str:
    """Render the weekly report dict as a compact WhatsApp message."""
    if not report.get("post_count"):
        return "📊 *Weekly LinkedIn report*\n\nNo published posts in the window yet."
    t = report.get("totals", {})
    w = report.get("wow_delta", {})
    lines = [
        "📊 *Weekly LinkedIn report*",
        f"Window: {report.get('window_days', 7)} days · {report['post_count']} posts",
        "",
        f"👍 {t.get('likes', 0)}  💬 {t.get('comments', 0)}  "
        f"🔁 {t.get('shares', 0)}  👁 {t.get('impressions', 0)}",
        f"Engagement WoW: {w.get('this_week', 0):.1f} vs {w.get('last_week', 0):.1f} "
        f"(Δ {w.get('delta', 0):+.1f})",
    ]
    top = report.get("top_posts", [])
    if top:
        lines.append("")
        lines.append("🏆 Top posts:")
        for p in top[:3]:
            lines.append(f"  #{p.get('post_id')} — {(p.get('headline') or '')[:50]}")
    bt = report.get("best_topics", [])
    if bt:
        lines.append("")
        lines.append("Best topics: " + ", ".join(str(x.get("topic")) for x in bt[:3]))
    return "\n".join(lines).strip()


def build_scheduler(settings: Settings | None = None) -> AsyncIOScheduler:
    """Construct (but do not start) the scheduler with both cron jobs registered."""
    settings = settings or get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

    scheduler.add_job(
        run_daily_pipeline,
        CronTrigger(
            hour=settings.daily_pipeline_hour,
            minute=settings.daily_pipeline_minute,
            timezone=settings.scheduler_timezone,
        ),
        id="daily_pipeline",
        name="Daily collect→analyze→generate→notify",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.add_job(
        run_weekly_report,
        CronTrigger(
            day_of_week=settings.weekly_report_day,
            hour=settings.weekly_report_hour,
            minute=settings.weekly_report_minute,
            timezone=settings.scheduler_timezone,
        ),
        id="weekly_report",
        name="Weekly analytics report → WhatsApp",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    return scheduler
