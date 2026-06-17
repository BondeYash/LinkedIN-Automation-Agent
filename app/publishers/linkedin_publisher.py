"""LinkedIn publisher — the only path from APPROVED to live.

Guarantees:
- **Guard first.** The post is re-read from the DB inside `publish`; anything
  that is not `APPROVED` is refused. The caller is never trusted.
- **Retry only transient failures.** 5xx / timeout / 429 are retried with
  exponential backoff up to `publish_max_tries`; a 4xx (bad/expired token)
  fails fast — no point hammering an auth error.
- **Never crash the pipeline.** A final network failure is recorded as a
  FAILED `publishing_history` row and returned as a result; the post stays
  APPROVED so it can be retried later. Only the guard raises.
- **Text matches the approved preview.** `render_post_text` assembles the exact
  text the human saw in the dashboard (headline, hook, body, cta, hashtags).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.base import BasePublisher
from app.core.config import Settings, get_settings
from app.models.enums import PostStatus, PublishStatus
from app.models.models import GeneratedPost, PublishingHistory
from app.publishers.linkedin_client import LinkedInClient
from app.repositories.repos import AuditLogRepository, PostRepository, PublishingRepository
from app.utils.http import is_transient

logger = logging.getLogger(__name__)


class PostNotFound(LookupError):
    pass


class NotApproved(ValueError):
    """The post is not in APPROVED state; publishing is refused."""


@dataclass
class PublishResult:
    ok: bool
    post_id: int
    status: PostStatus
    linkedin_post_id: str | None = None
    error: str | None = None
    retries: int = 0


def render_post_text(post: GeneratedPost) -> str:
    """The final LinkedIn text — the same content the dashboard previewed:
    headline, then hook, body, cta (blank line between), then hashtags."""
    tags = " ".join(f"#{t}" for t in (post.hashtags or []))
    blocks = [post.headline, post.hook, post.body, post.cta, tags]
    return "\n\n".join(b.strip() for b in blocks if b and b.strip()).strip()


class LinkedInPublisher(BasePublisher):
    def __init__(
        self,
        posts: PostRepository,
        publishing: PublishingRepository,
        client: LinkedInClient | None = None,
        *,
        audit: AuditLogRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.posts = posts
        self.publishing = publishing
        self.settings = settings or get_settings()
        self.client = client or LinkedInClient(self.settings)
        self.audit = audit

    async def publish(self, post: GeneratedPost) -> PublishResult:
        """Publish an APPROVED post. Re-reads + guards before any network call."""
        fresh = self.posts.get(post.id)
        if fresh is None:
            raise PostNotFound(f"post {post.id} not found")
        if fresh.status != PostStatus.APPROVED:
            raise NotApproved(
                f"post {fresh.id} is {fresh.status.value}; only APPROVED posts may publish"
            )

        text = render_post_text(fresh)
        attempts = 0
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(is_transient),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
                stop=stop_after_attempt(self.settings.publish_max_tries),
                reraise=True,
            ):
                with attempt:
                    attempts = attempt.retry_state.attempt_number
                    linkedin_id = await self.client.create_post(text)
        except Exception as exc:  # transient budget exhausted or a fatal 4xx
            return self._record_failure(fresh, error=str(exc), retries=attempts - 1)

        return self._record_success(fresh, linkedin_id=linkedin_id, retries=attempts - 1)

    # --- persistence ---------------------------------------------------------

    def _record_success(self, post: GeneratedPost, *, linkedin_id: str, retries: int) -> PublishResult:
        self.publishing.create(
            PublishingHistory(
                post_id=post.id,
                linkedin_post_id=linkedin_id,
                status=PublishStatus.PUBLISHED,
                published_at=datetime.now(timezone.utc),
                retries=retries,
            )
        )
        post.status = PostStatus.PUBLISHED
        self.posts.update(post)
        self._audit(post, "post.published", {"linkedin_post_id": linkedin_id, "retries": retries})
        self.posts.db.commit()
        logger.info("Post %s published to LinkedIn (%s)", post.id, linkedin_id)
        return PublishResult(
            ok=True, post_id=post.id, status=post.status,
            linkedin_post_id=linkedin_id, retries=retries,
        )

    def _record_failure(self, post: GeneratedPost, *, error: str, retries: int) -> PublishResult:
        self.publishing.create(
            PublishingHistory(
                post_id=post.id,
                status=PublishStatus.FAILED,
                error=error,
                retries=retries,
            )
        )
        # Leave the post APPROVED so it can be retried; never advance to PUBLISHED.
        self._audit(post, "post.publish_failed", {"error": error, "retries": retries})
        self.posts.db.commit()
        logger.warning("Publish failed for post %s after %s retries: %s", post.id, retries, error)
        return PublishResult(
            ok=False, post_id=post.id, status=post.status, error=error, retries=retries,
        )

    def _audit(self, post: GeneratedPost, action: str, payload: dict) -> None:
        if self.audit is not None:
            self.audit.record(
                actor="system", action=action, entity=f"post:{post.id}", payload=payload
            )
