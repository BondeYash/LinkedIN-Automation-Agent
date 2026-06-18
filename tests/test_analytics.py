"""Phase 9 tests — analytics client parsing, sync, eng_rate, report, feedback.

All fakes: no network, no DB. Mirrors the Phase 8 publishing test style.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.analyzers.analytics_client import LinkedInAnalyticsClient, _parse_social
from app.analyzers.analytics_service import AnalyticsService, engagement_rate
from app.analyzers.feedback import FeedbackTuner
from app.analyzers.weekly_report import WeeklyReport
from app.core.config import Settings
from app.models.models import Analytics

NOW = datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc)


def _settings(**kw) -> Settings:
    base = dict(linkedin_access_token="tok", analytics_assumed_impressions=0)
    base.update(kw)
    return Settings(**base)


# --- client parsing ---------------------------------------------------------


def test_parse_social_reads_likes_and_comments():
    payload = {
        "likesSummary": {"totalLikes": 12},
        "commentsSummary": {"aggregatedTotalComments": 4},
    }
    assert _parse_social(payload) == (12, 4)


def test_parse_social_tolerates_alt_fields_and_missing():
    assert _parse_social({"likesSummary": {"aggregatedTotalLikes": 7}}) == (7, 0)
    assert _parse_social({}) == (0, 0)


async def test_client_unconfigured_raises():
    from app.analyzers.analytics_client import AnalyticsAuthError

    client = LinkedInAnalyticsClient(Settings(linkedin_access_token=""))
    assert client.configured() is False
    with pytest.raises(AnalyticsAuthError):
        await client.fetch("urn:li:share:1")


# --- engagement rate --------------------------------------------------------


def test_eng_rate_uses_weights_when_impressions_present():
    m = SimpleNamespace(likes=10, comments=2, shares=1, impressions=100)
    # (10 + 2*2 + 3*1)/100 = 17/100
    assert engagement_rate(m, _settings()) == 0.17


def test_eng_rate_zero_without_impressions():
    m = SimpleNamespace(likes=10, comments=2, shares=1, impressions=0)
    assert engagement_rate(m, _settings()) == 0.0


def test_eng_rate_falls_back_to_assumed_impressions():
    m = SimpleNamespace(likes=10, comments=0, shares=0, impressions=0)
    assert engagement_rate(m, _settings(analytics_assumed_impressions=1000)) == 0.01


# --- service sync -----------------------------------------------------------


class _FakeAnalyticsRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.added = []
        self.db = SimpleNamespace(commit=self._commit, _commits=0)

    def _commit(self):
        self.db._commits += 1

    def add(self, post_id, *, likes, comments, shares, impressions):
        row = Analytics(
            post_id=post_id, likes=likes, comments=comments, shares=shares, impressions=impressions
        )
        self.added.append(row)
        return row

    def latest_per_post(self):
        return self.rows

    def since(self, *, days):
        return self.rows


class _FakePublishingRepo:
    def __init__(self, mapping, latest=None):
        self._mapping = mapping
        self._latest = latest or {}

    def published_post_ids(self):
        return dict(self._mapping)

    def latest_for_post(self, post_id):
        return self._latest.get(post_id)


class _OkClient:
    def __init__(self, metrics):
        self._metrics = metrics
        self.calls = 0

    async def fetch(self, urn):
        self.calls += 1
        return self._metrics


class _BoomClient:
    async def fetch(self, urn):
        raise httpx.HTTPStatusError(
            "forbidden",
            request=httpx.Request("GET", "https://api.linkedin.com"),
            response=httpx.Response(403, request=httpx.Request("GET", "https://api.linkedin.com")),
        )


async def test_sync_appends_one_row_per_published_post():
    from app.analyzers.analytics_client import PostMetrics

    repo = _FakeAnalyticsRepo()
    pub = _FakePublishingRepo({1: "urn:li:share:1", 2: "urn:li:share:2"})
    client = _OkClient(PostMetrics(likes=5, comments=1, shares=0, impressions=0))
    svc = AnalyticsService(repo, pub, client, settings=_settings())

    result = await svc.sync()

    assert result.synced == 2 and result.errors == 0
    assert len(repo.added) == 2
    assert repo.db._commits == 1  # one commit for the whole run


async def test_sync_skips_failed_fetch_without_aborting():
    repo = _FakeAnalyticsRepo()
    pub = _FakePublishingRepo({1: "urn:li:share:1"})
    svc = AnalyticsService(repo, pub, _BoomClient(), settings=_settings())

    result = await svc.sync()

    assert result.synced == 0 and result.errors == 1
    assert repo.added == []


# --- weekly report ----------------------------------------------------------


def _analytics(post_id, likes, comments, shares=0, impressions=0, *, ts=NOW):
    a = Analytics(
        post_id=post_id, likes=likes, comments=comments, shares=shares, impressions=impressions
    )
    a.captured_at = ts
    return a


class _FakePostRepo:
    def __init__(self, posts):
        self._posts = posts

    def get(self, post_id):
        return self._posts.get(post_id)


def _post(headline, topic, hashtags, body="x" * 700, hour=9):
    return SimpleNamespace(
        headline=headline,
        topic=SimpleNamespace(name=topic),
        hashtags=hashtags,
        body=body,
        hook=None,
        best_time=datetime(2026, 6, 18, hour, 0, tzinfo=timezone.utc),
    )


def test_weekly_report_ranks_and_groups():
    rows = [_analytics(1, 20, 5), _analytics(2, 3, 0)]
    repo = _FakeAnalyticsRepo(rows)
    posts = _FakePostRepo(
        {
            1: _post("Winner", "AI", ["AI", "ML"]),
            2: _post("Quiet", "DevOps", ["DevOps"]),
        }
    )
    report = WeeklyReport(repo, posts, _FakePublishingRepo({}), settings=_settings()).build()

    assert report["post_count"] == 2
    assert report["top_posts"][0]["post_id"] == 1  # higher weighted engagement first
    assert report["totals"]["likes"] == 23
    topics = [t["topic"] for t in report["best_topics"]]
    assert topics[0] == "AI"


def test_weekly_report_empty_is_safe():
    report = WeeklyReport(
        _FakeAnalyticsRepo([]), _FakePostRepo({}), _FakePublishingRepo({}), settings=_settings()
    ).build()
    assert report["post_count"] == 0
    assert report["top_posts"] == []


def test_wow_delta_splits_windows():
    last = NOW - timedelta(days=10)
    rows = [_analytics(1, 10, 0, ts=last), _analytics(1, 30, 0, ts=NOW)]
    repo = _FakeAnalyticsRepo(rows)
    posts = _FakePostRepo({1: _post("P", "AI", ["AI"])})
    report = WeeklyReport(repo, posts, _FakePublishingRepo({}), settings=_settings()).build()
    wow = report["wow_delta"]
    assert wow["this_week"] == 30.0 and wow["last_week"] == 10.0
    assert wow["delta"] == 20.0


# --- feedback loop ----------------------------------------------------------


def test_feedback_skips_below_min_sample(tmp_path):
    path = tmp_path / "optimization.txt"
    posts = _FakePostRepo({})
    tuner = FeedbackTuner(posts, settings=_settings(feedback_min_posts=3), path=path)
    out = tuner.run({"top_posts": [{"post_id": 1}, {"post_id": 2}]})
    assert out is None and not path.exists()


def test_feedback_writes_hints(tmp_path):
    path = tmp_path / "optimization.txt"
    posts = _FakePostRepo(
        {
            1: _post("A", "AI", ["AI", "ML"], body="?" + "x" * 400),
            2: _post("B", "AI", ["AI", "Cloud"], body="x" * 450),
            3: _post("C", "Data", ["Data"], body="x" * 500),
        }
    )
    report = {
        "top_posts": [{"post_id": 1}, {"post_id": 2}, {"post_id": 3}],
        "best_topics": [{"topic": "AI"}],
        "best_hours": [{"hour": 9}],
        "best_hashtags": [{"hashtag": "AI"}],
    }
    tuner = FeedbackTuner(posts, settings=_settings(feedback_min_posts=3), path=path)
    out = tuner.run(report)

    assert out and path.exists()
    text = path.read_text()
    assert "OPTIMIZATION HINTS" in text
    assert "hashtags" in text.lower()
    assert "AI" in text
