"""Dashboard metrics — one consolidated payload for the analytics UI (Phase 13).

The web dashboard renders real charts (Plotly), so it needs aggregated, chart-ready
data in a single round-trip rather than many table endpoints. This builder assembles:

- KPI headline numbers (posts by lifecycle, articles, avg trend score, this-week
  engagement + WoW%).
- A post-lifecycle funnel (draft → pending/review → approved → published).
- News-collection velocity (articles/day by source) — the "what's the pipeline
  ingesting" view.
- An engagement time-series (weighted engagement/day from the analytics captures).
- A trend snapshot (top topics with their popularity/recency/relevance components)
  for a radar/bar.
- The reach insights already computed by WeeklyReport (best hours/topics/hashtags,
  top posts, totals, WoW) — reused verbatim so there's a single source of truth.

Everything is best-effort: a failing section degrades to empty, never 500s the page.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analyzers.weekly_report import WeeklyReport
from app.core.config import Settings, get_settings
from app.models.enums import PostStatus
from app.models.models import Analytics, Article, GeneratedPost, Topic, Trend

logger = logging.getLogger(__name__)

# Lifecycle order for the funnel chart.
_FUNNEL = [
    (PostStatus.DRAFT, "Draft"),
    (PostStatus.NEEDS_REVIEW, "Needs review"),
    (PostStatus.PENDING, "Pending"),
    (PostStatus.APPROVED, "Approved"),
    (PostStatus.PUBLISHED, "Published"),
]


class DashboardMetrics:
    def __init__(self, db: Session, report: WeeklyReport, settings: Settings | None = None) -> None:
        self.db = db
        self.report = report
        self.settings = settings or get_settings()

    def build(self) -> dict:
        report = self._safe(self.report.build, {})
        status_counts = self._status_counts()
        return {
            "kpis": self._kpis(status_counts, report),
            "funnel": [
                {"stage": label, "count": status_counts.get(status, 0)}
                for status, label in _FUNNEL
            ],
            "news_velocity": self._safe(self._news_velocity, []),
            "engagement_series": self._safe(self._engagement_series, []),
            "trend_snapshot": self._safe(self._trend_snapshot, []),
            # Reach insights straight from the weekly report (single source of truth).
            "best_hours": report.get("best_hours", []),
            "best_topics": report.get("best_topics", []),
            "best_hashtags": report.get("best_hashtags", []),
            "top_posts": report.get("top_posts", []),
            "totals": report.get("totals", {}),
            "wow_delta": report.get("wow_delta", {}),
            "window_days": report.get("window_days", self.settings.analytics_window_days),
        }

    # --- sections ------------------------------------------------------------

    def _status_counts(self) -> dict[PostStatus, int]:
        rows = self.db.execute(
            select(GeneratedPost.status, func.count()).group_by(GeneratedPost.status)
        ).all()
        return {status: count for status, count in rows}

    def _kpis(self, status_counts: dict, report: dict) -> dict:
        total_posts = sum(status_counts.values())
        articles = self.db.execute(select(func.count()).select_from(Article)).scalar() or 0
        avg_trend = self.db.execute(select(func.avg(Trend.score))).scalar()
        wow = report.get("wow_delta", {})
        return {
            "total_posts": total_posts,
            "published": status_counts.get(PostStatus.PUBLISHED, 0),
            "pending": status_counts.get(PostStatus.PENDING, 0)
            + status_counts.get(PostStatus.NEEDS_REVIEW, 0),
            "articles": articles,
            "avg_trend_score": round(float(avg_trend), 3) if avg_trend is not None else 0.0,
            "week_engagement": round(float(wow.get("this_week", 0.0)), 1),
            "wow_pct": wow.get("pct_change"),
        }

    def _news_velocity(self, *, days: int = 14) -> list[dict]:
        """Articles collected per day per source (last `days`)."""
        day = func.date(Article.collected_at)
        rows = self.db.execute(
            select(day, Article.source, func.count())
            .group_by(day, Article.source)
            .order_by(day)
        ).all()
        # Pivot to [{date, <source>: n, ...}] keeping only recent days.
        per_day: dict[str, dict] = defaultdict(dict)
        sources: set[str] = set()
        for d, source, count in rows:
            key = str(d)
            per_day[key][source] = count
            sources.add(source)
        recent = sorted(per_day.keys())[-days:]
        return [{"date": d, **{s: per_day[d].get(s, 0) for s in sorted(sources)}} for d in recent]

    def _engagement_series(self) -> list[dict]:
        """Weighted engagement summed per capture-day across the analytics history."""
        wc, ws = self.settings.eng_weight_comment, self.settings.eng_weight_share
        day = func.date(Analytics.captured_at)
        weighted = (
            func.sum(Analytics.likes)
            + wc * func.sum(Analytics.comments)
            + ws * func.sum(Analytics.shares)
        )
        rows = self.db.execute(
            select(
                day,
                weighted,
                func.sum(Analytics.likes),
                func.sum(Analytics.comments),
                func.sum(Analytics.shares),
            )
            .group_by(day)
            .order_by(day)
        ).all()
        return [
            {
                "date": str(d),
                "engagement": round(float(w or 0), 1),
                "likes": int(likes or 0),
                "comments": int(comments or 0),
                "shares": int(shares or 0),
            }
            for d, w, likes, comments, shares in rows
        ]

    def _trend_snapshot(self, *, limit: int = 8) -> list[dict]:
        """Most recent run's top trends with their component scores (for a radar/bar)."""
        latest_run = self.db.execute(select(func.max(Trend.run_date))).scalar()
        if latest_run is None:
            return []
        rows = self.db.execute(
            select(Trend, Topic.name)
            .join(Topic, Trend.topic_id == Topic.id)
            .where(Trend.run_date == latest_run)
            .order_by(Trend.score.desc())
            .limit(limit)
        ).all()
        return [
            {
                "topic": name,
                "score": round(float(t.score), 3),
                "popularity": round(float(t.popularity), 3),
                "recency": round(float(t.recency), 3),
                "relevance": round(float(t.relevance), 3),
            }
            for t, name in rows
        ]

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            logger.warning("dashboard metric section failed: %s", getattr(fn, "__name__", fn), exc_info=True)
            return default
