"""Generation route — turn a topic into a grounded DRAFT post."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_article_repo,
    get_post_repo,
    get_style_repo,
    get_topic_repo,
)
from app.repositories.repos import (
    ArticleRepository,
    PostRepository,
    StyleProfileRepository,
    TopicRepository,
)
from app.ai.dedup import PostDedup
from app.ai.factcheck import FactChecker
from app.core.config import get_settings
from app.schemas.post import GenerateRequest, PostOut
from app.services.generator_service import GeneratorService, TopicNotFound

router = APIRouter(prefix="/generate", tags=["generate"])


@router.post("", response_model=PostOut)
async def generate_post(
    body: GenerateRequest,
    topics: TopicRepository = Depends(get_topic_repo),
    articles: ArticleRepository = Depends(get_article_repo),
    styles: StyleProfileRepository = Depends(get_style_repo),
    posts: PostRepository = Depends(get_post_repo),
) -> PostOut:
    """Generate an original, RAG-grounded LinkedIn draft for a topic. Saved as
    DRAFT; it must pass quality gates (Phase 6) and human approval (Phase 7)
    before it can publish."""
    settings = get_settings()
    dedup = factcheck = None
    if settings.quality_gates_enabled:
        dedup = PostDedup(settings=settings)
        factcheck = FactChecker(settings=settings)
    service = GeneratorService(
        topics, articles, styles, posts, dedup=dedup, factcheck=factcheck
    )
    try:
        post = await service.generate(body.topic_id, style_name=body.style_name)
    except TopicNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:  # LLM returned unparseable output
        raise HTTPException(status_code=502, detail=f"generation failed: {exc}") from exc
    return PostOut.model_validate(post)
