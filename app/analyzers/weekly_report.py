"""Weekly engagement report — what worked, and how this week compares to last.

Built from the append-only `analytics` time-series with pandas:
- **Top posts** this week by engagement.
- **Week-over-week delta** in total weighted engagement.
- **Best topics / hashtags / post hours** — the patterns the feedback loop
  (`feedback.py`) writes back into the generator.

Returns a plain JSON-serializable dict; the route hands it straight to the API
and the dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from app.analyzers.analytics_service import engagement_rate
from app.core.config import Settings, get_settings
from app.models.models import Analytics
from app.repositories.repos import (
    AnalyticsRepository,
    PostRepository,
    PublishingRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class _Meta:
    headline: str
    topic: str | None
    hashtags: list[str]
    hour: int | None


class WeeklyReport:
    def __init__(
        self,
        analytics: AnalyticsRepository,
        posts: PostRepository,
        publishing: PublishingRepository,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.analytics = analytics
        self.posts = posts
        self.publishing = publishing
        self.settings = settings or get_settings()

    # --- public --------------------------------------------------------------

    def build(self) -> dict:
        window = self.settings.analytics_window_days
        latest = self.analytics.latest_per_post()
        if not latest:
            return _empty(window)

        df = self._frame(latest)
        return {
            "window_days": window,
            "post_count": int(len(df)),
            "totals": self._totals(df),
            "wow_delta": self._wow_delta(window),
            "top_posts": self._top_posts(df),
            "best_topics": self._group_mean(df, "topic"),
            "best_hashtags": self._best_hashtags(df),
            "best_hours": self._group_mean(df, "hour"),
        }

    # --- frame building ------------------------------------------------------

    def _meta(self, post_id: int) -> _Meta:
        post = self.posts.get(post_id)
        hist = self.publishing.latest_for_post(post_id)
        published_at = hist.published_at if hist else None
        hour = published_at.hour if published_at else (
            post.best_time.hour if post and post.best_time else None
        )
        return _Meta(
            headline=(post.headline if post and post.headline else f"post {post_id}"),
            topic=(post.topic.name if post and post.topic else None),
            hashtags=list(post.hashtags) if post and post.hashtags else [],
            hour=hour,
        )

    def _frame(self, rows: list[Analytics]) -> pd.DataFrame:
        records = []
        for a in rows:
            m = self._meta(a.post_id)
            records.append(
                {
                    "post_id": a.post_id,
                    "headline": m.headline,
                    "topic": m.topic,
                    "hashtags": m.hashtags,
                    "hour": m.hour,
                    "likes": a.likes,
                    "comments": a.comments,
                    "shares": a.shares,
                    "impressions": a.impressions,
                    "eng_rate": engagement_rate(a, self.settings),
                    "weighted": (
                        a.likes
                        + self.settings.eng_weight_comment * a.comments
                        + self.settings.eng_weight_share * a.shares
                    ),
                }
            )
        return pd.DataFrame.from_records(records)

    # --- sections ------------------------------------------------------------

    @staticmethod
    def _totals(df: pd.DataFrame) -> dict:
        return {
            "likes": int(df["likes"].sum()),
            "comments": int(df["comments"].sum()),
            "shares": int(df["shares"].sum()),
            "impressions": int(df["impressions"].sum()),
            "weighted_engagement": float(df["weighted"].sum()),
        }

    def _top_posts(self, df: pd.DataFrame) -> list[dict]:
        # Rank by eng_rate when impressions exist, else by raw weighted engagement.
        rank_col = "eng_rate" if df["eng_rate"].sum() > 0 else "weighted"
        top = df.sort_values(rank_col, ascending=False).head(self.settings.feedback_top_n)
        return [
            {
                "post_id": int(r.post_id),
                "headline": r.headline,
                "topic": r.topic,
                "likes": int(r.likes),
                "comments": int(r.comments),
                "shares": int(r.shares),
                "eng_rate": float(r.eng_rate),
                "weighted_engagement": float(r.weighted),
            }
            for r in top.itertuples()
        ]

    @staticmethod
    def _group_mean(df: pd.DataFrame, col: str) -> list[dict]:
        """Mean weighted engagement grouped by a column (topic / hour), best first."""
        sub = df[df[col].notna()]
        if sub.empty:
            return []
        grouped = (
            sub.groupby(col)["weighted"].agg(["mean", "count"]).sort_values("mean", ascending=False)
        )
        return [
            {col: _key(idx), "avg_engagement": round(float(row["mean"]), 2), "posts": int(row["count"])}
            for idx, row in grouped.iterrows()
        ]

    @staticmethod
    def _best_hashtags(df: pd.DataFrame) -> list[dict]:
        exploded = df.explode("hashtags")
        exploded = exploded[exploded["hashtags"].notna()]
        if exploded.empty:
            return []
        grouped = (
            exploded.groupby("hashtags")["weighted"]
            .agg(["mean", "count"])
            .sort_values("mean", ascending=False)
            .head(10)
        )
        return [
            {"hashtag": str(tag), "avg_engagement": round(float(row["mean"]), 2), "posts": int(row["count"])}
            for tag, row in grouped.iterrows()
        ]

    def _wow_delta(self, window: int) -> dict:
        """Total weighted engagement this window vs the previous one.

        For each post we take its newest capture inside a window (cumulative
        counts → newest = standing at window end), weight it, and sum across
        posts. The delta is this-window-sum minus last-window-sum.
        """
        rows = self.analytics.since(days=2 * window)
        if not rows:
            return {"this_week": 0.0, "last_week": 0.0, "delta": 0.0, "pct_change": None}

        recs = [
            {
                "post_id": a.post_id,
                "captured_at": pd.Timestamp(a.captured_at),
                "weighted": (
                    a.likes
                    + self.settings.eng_weight_comment * a.comments
                    + self.settings.eng_weight_share * a.shares
                ),
            }
            for a in rows
        ]
        df = pd.DataFrame.from_records(recs)
        boundary = df["captured_at"].max() - pd.Timedelta(days=window)

        def _window_sum(frame: pd.DataFrame) -> float:
            if frame.empty:
                return 0.0
            newest = frame.sort_values("captured_at").groupby("post_id")["weighted"].last()
            return float(newest.sum())

        this_week = _window_sum(df[df["captured_at"] > boundary])
        last_week = _window_sum(df[df["captured_at"] <= boundary])
        delta = this_week - last_week
        pct = round((delta / last_week) * 100, 1) if last_week > 0 else None
        return {
            "this_week": round(this_week, 2),
            "last_week": round(last_week, 2),
            "delta": round(delta, 2),
            "pct_change": pct,
        }


def _key(value):
    """JSON-friendly group key (numpy int hour -> python int)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _empty(window: int) -> dict:
    return {
        "window_days": window,
        "post_count": 0,
        "totals": {"likes": 0, "comments": 0, "shares": 0, "impressions": 0, "weighted_engagement": 0.0},
        "wow_delta": {"this_week": 0.0, "last_week": 0.0, "delta": 0.0, "pct_change": None},
        "top_posts": [],
        "best_topics": [],
        "best_hashtags": [],
        "best_hours": [],
    }
