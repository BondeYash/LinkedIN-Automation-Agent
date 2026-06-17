"""Publishing route — push an APPROVED post to LinkedIn.

`POST /publish/{post_id}` is guarded twice: the route requires an editor/admin
JWT, and the publisher re-reads the post and refuses anything that is not
APPROVED. A transient API failure is recorded and returned as `ok: false`
(HTTP 200) rather than crashing — the post stays APPROVED for a later retry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_linkedin_publisher, get_post_repo, require_role
from app.models.enums import UserRole
from app.models.models import User
from app.publishers.linkedin_publisher import (
    LinkedInPublisher,
    NotApproved,
    PostNotFound,
)
from app.repositories.repos import PostRepository
from app.schemas.publishing import PublishResultOut

router = APIRouter(prefix="/publish", tags=["publishing"])

_editor = require_role(UserRole.EDITOR)


@router.post("/{post_id}", response_model=PublishResultOut)
async def publish(
    post_id: int,
    publisher: LinkedInPublisher = Depends(get_linkedin_publisher),
    posts: PostRepository = Depends(get_post_repo),
    user: User = Depends(_editor),
) -> PublishResultOut:
    post = posts.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"post {post_id} not found")
    try:
        result = await publisher.publish(post)
    except PostNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotApproved as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PublishResultOut(**result.__dict__)
