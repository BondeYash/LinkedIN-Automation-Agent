"""Phase 7 tests — JWT helpers, approval-service transitions, notification fan-out.

All use fakes (no DB / no network), matching the rest of the suite.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_action_token,
    decode_access_token,
    decode_action_token,
)
from app.models.enums import (
    ApprovalAction,
    NotificationChannel,
    NotificationStatus,
    PostStatus,
    UserRole,
)
from app.models.models import GeneratedPost, Notification, User
from app.notifications.service import NotificationService, build_notifiers
from app.services.approval_service import (
    ApprovalService,
    InvalidTransition,
    PostNotFound,
)

# --- JWT --------------------------------------------------------------------


def test_access_token_roundtrip():
    tok = create_access_token(user_id=42, role="admin")
    claims = decode_access_token(tok)
    assert claims["sub"] == "42" and claims["role"] == "admin"


def test_expired_token_rejected():
    s = Settings(access_token_expire_minutes=-1)  # already expired
    tok = create_access_token(user_id=1, role="viewer", settings=s)
    with pytest.raises(TokenError):
        decode_access_token(tok, s)


def test_tampered_token_rejected():
    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt")


def test_action_token_type_is_enforced():
    access = create_access_token(user_id=1, role="admin")
    with pytest.raises(TokenError):
        decode_action_token(access)  # access token is not an action token
    action = create_action_token(post_id=7, action="approve")
    claims = decode_action_token(action)
    assert claims["post_id"] == 7 and claims["action"] == "approve"


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

    def review_queue(self, *, limit=100):
        return [self._post] if self._post else []


class _FakeApprovalRepo:
    def __init__(self):
        self.saved = []

    def create(self, obj, *, commit=False):
        obj.id = len(self.saved) + 1
        self.saved.append(obj)
        return obj


class _FakeAuditRepo:
    def __init__(self):
        self.records = []

    def record(self, *, actor, action, entity, payload=None):
        self.records.append((actor, action, entity, payload))
        return None


class _FakeNotifier:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, post):
        self.dispatched.append(post.id)
        return []


def _post(status=PostStatus.PENDING):
    p = GeneratedPost(body="A grounded post body.", status=status, hashtags=["AI"])
    p.id = 5
    return p


def _user():
    u = User(email="editor@example.com", hashed_pw="x", role=UserRole.EDITOR)
    u.id = 3
    return u


def _service(post, *, notifier=None):
    return ApprovalService(
        _FakePostRepo(post), _FakeApprovalRepo(), _FakeAuditRepo(), notifier=notifier
    )


# --- approval transitions ---------------------------------------------------


def test_submit_moves_to_pending_and_notifies():
    post = _post(PostStatus.NEEDS_REVIEW)
    notifier = _FakeNotifier()
    svc = _service(post, notifier=notifier)
    out = svc.submit(5, user=_user())
    assert out.status == PostStatus.PENDING
    assert notifier.dispatched == [5]
    assert any(a == "post.submitted" for _, a, _, _ in svc.audit.records)


def test_approve_sets_status_and_logs():
    post = _post(PostStatus.PENDING)
    svc = _service(post)
    out = svc.approve(5, user=_user(), comment="ship it")
    assert out.status == PostStatus.APPROVED
    assert len(svc.approvals.saved) == 1
    saved = svc.approvals.saved[0]
    assert saved.action == ApprovalAction.APPROVE and saved.comment == "ship it"
    assert any(a == "post.approve" for _, a, _, _ in svc.audit.records)


def test_reject_and_regenerate_change_status():
    assert _service(_post()).reject(5, user=_user()).status == PostStatus.REJECTED
    assert _service(_post()).regenerate(5, user=_user()).status == PostStatus.REGENERATE


def test_edit_applies_fields_and_marks_edited():
    post = _post(PostStatus.PENDING)
    svc = _service(post)
    out = svc.edit(5, changes={"headline": "New head", "body": "New body"}, user=_user())
    assert out.status == PostStatus.EDITED
    assert out.headline == "New head" and out.body == "New body"
    assert svc.approvals.saved[0].action == ApprovalAction.EDIT


def test_edit_without_fields_raises():
    with pytest.raises(InvalidTransition):
        _service(_post(PostStatus.PENDING)).edit(5, changes={}, user=_user())


def test_action_on_finished_post_rejected():
    post = _post(PostStatus.APPROVED)  # terminal
    with pytest.raises(InvalidTransition):
        _service(post).approve(5, user=_user())


def test_unknown_post_raises():
    with pytest.raises(PostNotFound):
        _service(None).approve(999, user=_user())


# --- notifications ----------------------------------------------------------


class _FakeNotifRepo:
    def __init__(self):
        self.saved = []

    def create(self, obj, *, commit=False):
        self.saved.append(obj)
        return obj


class _OkChannel:
    channel = NotificationChannel.LOG

    def __init__(self):
        self.calls = 0

    def enabled(self):
        return True

    def send(self, payload):
        self.calls += 1


class _BadChannel:
    channel = NotificationChannel.TEAMS

    def enabled(self):
        return True

    def send(self, payload):
        raise RuntimeError("webhook down")


def test_default_notifiers_always_include_log():
    notifiers = build_notifiers(Settings(notification_channels="log"))
    assert any(n.channel == NotificationChannel.LOG for n in notifiers)


def test_dispatch_records_sent_and_failed_per_channel():
    repo = _FakeNotifRepo()
    ok, bad = _OkChannel(), _BadChannel()
    svc = NotificationService(repo, settings=Settings(), notifiers=[ok, bad])
    rows: list[Notification] = svc.dispatch(_post())
    assert ok.calls == 1
    statuses = {r.channel: r.status for r in rows}
    assert statuses[NotificationChannel.LOG] == NotificationStatus.SENT
    assert statuses[NotificationChannel.TEAMS] == NotificationStatus.FAILED


def test_dispatch_builds_signed_action_links():
    repo = _FakeNotifRepo()
    captured = {}

    class _Capture:
        channel = NotificationChannel.LOG

        def enabled(self):
            return True

        def send(self, payload):
            captured.update(payload.links)

    NotificationService(repo, settings=Settings(), notifiers=[_Capture()]).dispatch(_post())
    assert set(captured) == {"approve", "reject", "regenerate"}
    # links carry a decodable action token
    token = captured["approve"].split("token=")[1]
    assert decode_action_token(token)["action"] == "approve"
