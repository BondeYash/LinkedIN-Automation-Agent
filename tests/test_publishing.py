"""Phase 8 tests — LinkedIn publisher guard, retry, persistence, text assembly.

All fakes: no network, no DB. A fake async client stands in for LinkedIn.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.models.enums import PostStatus, PublishStatus
from app.models.models import GeneratedPost
from app.publishers.linkedin_publisher import (
    LinkedInPublisher,
    NotApproved,
    PostNotFound,
    render_post_text,
)

# --- text assembly ----------------------------------------------------------


def test_render_matches_preview_order():
    post = GeneratedPost(
        headline="Big News", hook="A hook.", body="The body.", cta="Follow me.",
        hashtags=["AI", "Tech"],
    )
    text = render_post_text(post)
    assert text == "Big News\n\nA hook.\n\nThe body.\n\nFollow me.\n\n#AI #Tech"


def test_render_skips_empty_parts():
    post = GeneratedPost(body="Just a body.", hashtags=[])
    assert render_post_text(post) == "Just a body."


# --- fakes ------------------------------------------------------------------


class _FakeDB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class _FakePostRepo:
    def __init__(self, post):
        self._post = post
        self.db = _FakeDB()

    def get(self, post_id):
        return self._post if (self._post and self._post.id == post_id) else None

    def update(self, obj, *, commit=False):
        return obj


class _FakePublishRepo:
    def __init__(self):
        self.saved = []

    def create(self, obj, *, commit=False):
        self.saved.append(obj)
        return obj


class _FakeAuditRepo:
    def __init__(self):
        self.records = []

    def record(self, *, actor, action, entity, payload=None):
        self.records.append((actor, action, entity, payload))


class _OkClient:
    def __init__(self, post_id="urn:li:share:123"):
        self.post_id = post_id
        self.calls = 0

    async def create_post(self, text):
        self.calls += 1
        return self.post_id


class _FlakyClient:
    """Fails `fail_times` with a transient error, then succeeds."""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    async def create_post(self, text):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise httpx.TimeoutException("slow")
        return "urn:li:share:ok"


class _AuthErrorClient:
    def __init__(self):
        self.calls = 0

    async def create_post(self, text):
        self.calls += 1
        req = httpx.Request("POST", "https://api.linkedin.com/v2/ugcPosts")
        resp = httpx.Response(401, request=req)
        raise httpx.HTTPStatusError("unauthorized", request=req, response=resp)


def _post(status=PostStatus.APPROVED):
    p = GeneratedPost(headline="H", body="Body.", status=status, hashtags=["AI"])
    p.id = 5
    return p


def _publisher(post, client, *, max_tries=5):
    posts, pub, audit = _FakePostRepo(post), _FakePublishRepo(), _FakeAuditRepo()
    p = LinkedInPublisher(
        posts, pub, client, audit=audit, settings=Settings(publish_max_tries=max_tries)
    )
    return p, posts, pub, audit


# --- guard ------------------------------------------------------------------


async def test_non_approved_is_refused():
    pub, posts, _, _ = _publisher(_post(PostStatus.DRAFT), _OkClient())
    with pytest.raises(NotApproved):
        await pub.publish(posts.get(5))


async def test_unknown_post_raises():
    pub, _, _, _ = _publisher(None, _OkClient())
    ghost = GeneratedPost(body="x")
    ghost.id = 999
    with pytest.raises(PostNotFound):
        await pub.publish(ghost)


# --- success ----------------------------------------------------------------


async def test_publish_success_writes_history_and_marks_published():
    post = _post()
    pub, posts, publish_repo, audit = _publisher(post, _OkClient())
    result = await pub.publish(post)

    assert result.ok and result.linkedin_post_id == "urn:li:share:123"
    assert post.status == PostStatus.PUBLISHED
    row = publish_repo.saved[0]
    assert row.status == PublishStatus.PUBLISHED
    assert row.linkedin_post_id == "urn:li:share:123" and row.published_at is not None
    assert result.retries == 0
    assert any(a == "post.published" for _, a, _, _ in audit.records)
    assert posts.db.commits == 1


async def test_transient_error_retried_then_succeeds():
    post = _post()
    pub, _, publish_repo, _ = _publisher(post, _FlakyClient(fail_times=1), max_tries=3)
    result = await pub.publish(post)
    assert result.ok and result.retries == 1
    assert publish_repo.saved[0].status == PublishStatus.PUBLISHED


# --- failure ----------------------------------------------------------------


async def test_exhausted_transient_records_failure_and_keeps_approved():
    post = _post()
    pub, _, publish_repo, audit = _publisher(post, _FlakyClient(fail_times=99), max_tries=1)
    result = await pub.publish(post)

    assert not result.ok and result.error
    assert post.status == PostStatus.APPROVED  # left retryable, never PUBLISHED
    assert publish_repo.saved[0].status == PublishStatus.FAILED
    assert any(a == "post.publish_failed" for _, a, _, _ in audit.records)


async def test_auth_4xx_fails_fast_without_retry():
    post = _post()
    client = _AuthErrorClient()
    pub, _, publish_repo, _ = _publisher(post, client, max_tries=5)
    result = await pub.publish(post)

    assert not result.ok
    assert client.calls == 1  # 4xx not retried despite max_tries=5
    assert publish_repo.saved[0].status == PublishStatus.FAILED
    assert post.status == PostStatus.APPROVED
