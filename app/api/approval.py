"""Approval routes — the human review queue and the four decision actions.

Two ways to act:
- Authenticated JSON API (`/approvals/...`) used by the dashboard, protected by a
  login JWT and an editor/admin role.
- One-click `/approvals/action` links sent in notifications, authenticated by a
  short-lived signed action token instead of a login.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api.deps import get_approval_service, require_role
from app.core.security import TokenError, decode_action_token
from app.models.enums import UserRole
from app.models.models import User
from app.schemas.approval import ApprovalCard, DecisionRequest, EditRequest
from app.services.approval_service import (
    ApprovalService,
    InvalidTransition,
    PostNotFound,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])

# Editors and admins may act on drafts.
_editor = require_role(UserRole.EDITOR)


def _run(fn, *args, **kwargs):
    """Call a service method, translating domain errors to HTTP."""
    try:
        return fn(*args, **kwargs)
    except PostNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[ApprovalCard])
def list_pending(
    service: ApprovalService = Depends(get_approval_service),
    user: User = Depends(_editor),
    limit: int = Query(default=100, le=200),
) -> list[ApprovalCard]:
    """Drafts awaiting a decision, newest first, with trend score + quality flags."""
    return [ApprovalCard.from_post(p) for p in service.queue(limit=limit)]


@router.post("/{post_id}/submit", response_model=ApprovalCard)
def submit(
    post_id: int,
    service: ApprovalService = Depends(get_approval_service),
    user: User = Depends(_editor),
) -> ApprovalCard:
    """Send a draft into PENDING and notify the approvers."""
    return ApprovalCard.from_post(_run(service.submit, post_id, user=user))


@router.post("/{post_id}/approve", response_model=ApprovalCard)
def approve(
    post_id: int,
    body: DecisionRequest = DecisionRequest(),
    service: ApprovalService = Depends(get_approval_service),
    user: User = Depends(_editor),
) -> ApprovalCard:
    return ApprovalCard.from_post(_run(service.approve, post_id, user=user, comment=body.comment))


@router.post("/{post_id}/reject", response_model=ApprovalCard)
def reject(
    post_id: int,
    body: DecisionRequest = DecisionRequest(),
    service: ApprovalService = Depends(get_approval_service),
    user: User = Depends(_editor),
) -> ApprovalCard:
    return ApprovalCard.from_post(_run(service.reject, post_id, user=user, comment=body.comment))


@router.post("/{post_id}/regenerate", response_model=ApprovalCard)
def regenerate(
    post_id: int,
    body: DecisionRequest = DecisionRequest(),
    service: ApprovalService = Depends(get_approval_service),
    user: User = Depends(_editor),
) -> ApprovalCard:
    return ApprovalCard.from_post(_run(service.regenerate, post_id, user=user, comment=body.comment))


@router.post("/{post_id}/edit", response_model=ApprovalCard)
def edit(
    post_id: int,
    body: EditRequest,
    service: ApprovalService = Depends(get_approval_service),
    user: User = Depends(_editor),
) -> ApprovalCard:
    changes = body.model_dump(exclude={"comment"}, exclude_none=True)
    return ApprovalCard.from_post(
        _run(service.edit, post_id, changes=changes, user=user, comment=body.comment)
    )


_ACTION_FN = {"approve": "approve", "reject": "reject", "regenerate": "regenerate"}


@router.get("/action", response_class=HTMLResponse)
def one_click_action(
    token: str = Query(...),
    service: ApprovalService = Depends(get_approval_service),
) -> HTMLResponse:
    """Token-authenticated one-click action from a notification link (no login)."""
    try:
        claims = decode_action_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid action link: {exc}") from exc
    action = claims.get("action")
    if action not in _ACTION_FN:
        raise HTTPException(status_code=400, detail="unknown action")
    post = _run(getattr(service, _ACTION_FN[action]), int(claims["post_id"]), user=None)
    return HTMLResponse(
        f"<h2>Post #{post.id} — {post.status.value}</h2>"
        f"<p>Action '{action}' recorded. You can close this tab.</p>"
    )
