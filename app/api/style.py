"""Style routes — build a style profile from samples and list profiles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.analyzers.style_analyzer import StyleAnalyzer
from app.api.deps import get_style_repo
from app.repositories.repos import StyleProfileRepository
from app.schemas.style import StyleAnalyzeRequest, StyleProfileOut
from seed.sample_posts import SAMPLE_POSTS

router = APIRouter(prefix="/style", tags=["style"])


@router.post("/analyze", response_model=StyleProfileOut)
async def analyze_style(
    body: StyleAnalyzeRequest,
    styles: StyleProfileRepository = Depends(get_style_repo),
) -> StyleProfileOut:
    """Extract style features from sample posts and upsert a named profile.
    Falls back to seed reference posts when none are supplied. LLM labels are
    stubbed until Phase 5."""
    texts = body.posts or SAMPLE_POSTS
    analyzer = StyleAnalyzer(styles)
    try:
        profile = await analyzer.build(texts, name=body.name, source=body.source or "api")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StyleProfileOut.model_validate(profile)


@router.get("", response_model=list[StyleProfileOut])
def list_styles(
    styles: StyleProfileRepository = Depends(get_style_repo),
) -> list[StyleProfileOut]:
    """List saved style profiles."""
    return [StyleProfileOut.model_validate(p) for p in styles.list(limit=100)]
