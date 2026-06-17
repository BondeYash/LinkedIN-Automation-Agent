"""Approval workflow — the human gate every post must pass before publishing.

Each action (submit / approve / reject / edit / regenerate) changes the post
status, records who/when in `approvals`, and writes an `audit_logs` row, so the
whole decision history is reconstructable. Submitting a draft also fans a
notification out to the configured channels.

Status flow:  DRAFT | NEEDS_REVIEW --submit--> PENDING
              PENDING --> APPROVED | REJECTED | EDITED | REGENERATE
"""

from __future__ import annotations

import logging

from app.models.enums import ApprovalAction, PostStatus
from app.models.models import Approval, GeneratedPost, User
from app.repositories.repos import (
    ApprovalRepository,
    AuditLogRepository,
    PostRepository,
)

logger = logging.getLogger(__name__)


class PostNotFound(LookupError):
    pass


class InvalidTransition(ValueError):
    """Action not allowed from the post's current status."""


# Statuses from which a human decision may still be taken.
_ACTIONABLE = {
    PostStatus.DRAFT,
    PostStatus.NEEDS_REVIEW,
    PostStatus.PENDING,
    PostStatus.EDITED,
    PostStatus.REGENERATE,
}
_EDITABLE_FIELDS = ("headline", "hook", "body", "cta", "hashtags")


class ApprovalService:
    def __init__(
        self,
        posts: PostRepository,
        approvals: ApprovalRepository,
        audit: AuditLogRepository,
        *,
        notifier=None,  # app.notifications.service.NotificationService | None
    ) -> None:
        self.posts = posts
        self.approvals = approvals
        self.audit = audit
        self.notifier = notifier

    # --- queries -------------------------------------------------------------

    def queue(self, *, limit: int = 100) -> list[GeneratedPost]:
        return self.posts.review_queue(limit=limit)

    def get(self, post_id: int) -> GeneratedPost:
        post = self.posts.get(post_id)
        if post is None:
            raise PostNotFound(f"post {post_id} not found")
        return post

    # --- transitions ---------------------------------------------------------

    def submit(self, post_id: int, *, user: User | None = None) -> GeneratedPost:
        """Move a draft into PENDING and notify the approvers."""
        post = self.get(post_id)
        post.status = PostStatus.PENDING
        self.posts.update(post)
        self.audit.record(
            actor=_actor(user), action="post.submitted",
            entity=f"post:{post.id}", payload={"status": post.status.value},
        )
        self.posts.db.commit()
        if self.notifier is not None:
            try:
                self.notifier.dispatch(post)
                self.posts.db.commit()
            except Exception:  # notification failure must not lose the PENDING state
                logger.warning("Dispatch failed for post %s", post.id, exc_info=True)
        return post

    def approve(self, post_id: int, *, user: User | None = None, comment: str | None = None) -> GeneratedPost:
        return self._decide(post_id, PostStatus.APPROVED, ApprovalAction.APPROVE, user, comment)

    def reject(self, post_id: int, *, user: User | None = None, comment: str | None = None) -> GeneratedPost:
        return self._decide(post_id, PostStatus.REJECTED, ApprovalAction.REJECT, user, comment)

    def regenerate(self, post_id: int, *, user: User | None = None, comment: str | None = None) -> GeneratedPost:
        return self._decide(post_id, PostStatus.REGENERATE, ApprovalAction.REGENERATE, user, comment)

    def edit(
        self, post_id: int, *, changes: dict, user: User | None = None, comment: str | None = None
    ) -> GeneratedPost:
        """Apply a human's text edits and mark the post EDITED (still needs a final
        approve to publish)."""
        post = self._guard(post_id)
        applied = {}
        for field in _EDITABLE_FIELDS:
            if field in changes and changes[field] is not None:
                setattr(post, field, changes[field])
                applied[field] = changes[field]
        if not applied:
            raise InvalidTransition("no editable fields supplied")
        post.status = PostStatus.EDITED
        self.posts.update(post)
        self._record(post, ApprovalAction.EDIT, user, comment, extra={"fields": list(applied)})
        self.posts.db.commit()
        return post

    # --- internals -----------------------------------------------------------

    def _guard(self, post_id: int) -> GeneratedPost:
        post = self.get(post_id)
        if post.status not in _ACTIONABLE:
            raise InvalidTransition(
                f"post {post_id} is {post.status.value}; no action allowed"
            )
        return post

    def _decide(
        self, post_id: int, new_status: PostStatus, action: ApprovalAction,
        user: User | None, comment: str | None,
    ) -> GeneratedPost:
        post = self._guard(post_id)
        post.status = new_status
        self.posts.update(post)
        self._record(post, action, user, comment)
        self.posts.db.commit()
        logger.info("Post %s -> %s by %s", post.id, new_status.value, _actor(user))
        return post

    def _record(
        self, post: GeneratedPost, action: ApprovalAction, user: User | None,
        comment: str | None, *, extra: dict | None = None,
    ) -> Approval:
        approval = self.approvals.create(
            Approval(
                post_id=post.id,
                user_id=user.id if user else None,
                action=action,
                comment=comment,
            )
        )
        self.audit.record(
            actor=_actor(user),
            action=f"post.{action.value}",
            entity=f"post:{post.id}",
            payload={"status": post.status.value, **(extra or {})},
        )
        return approval


def _actor(user: User | None) -> str:
    return user.email if user else "system"
