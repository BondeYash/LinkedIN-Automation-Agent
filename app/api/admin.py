"""Admin dashboard — server-rendered approval console.

Renders a single Jinja2 page: a login box, the pending-draft queue (trend score,
quality flags, preview), and the four action buttons. The page calls the JSON
approval API with the login JWT, so the same endpoints back both the UI and any
notification one-click links.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))

router = APIRouter(tags=["admin"])


@router.get("/admin", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(request, "dashboard.html")
