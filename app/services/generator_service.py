"""Content generator — turn a topic into a grounded LinkedIn draft.

Flow: pull topic + trend + style profile + RAG grounding facts → fill the
editable prompt template → call the LLM (JSON mode) → parse structured output →
save a `generated_posts` row as DRAFT.

The draft is never auto-published: it enters the approval flow (Phase 7).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.ai.ollama_client import LLMClient, OllamaClient
from app.ai.rag import ChromaRAG, GroundingFact
from app.core.config import Settings, get_settings
from app.models.enums import PostStatus
from app.models.models import GeneratedPost, Topic
from app.repositories.repos import (
    ArticleRepository,
    PostRepository,
    StyleProfileRepository,
    TopicRepository,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "ai" / "prompts" / "generation.txt"
_REQUIRED_KEYS = ("headline", "hook", "body", "cta", "hashtags")


class TopicNotFound(LookupError):
    pass


@lru_cache(maxsize=4)
def _load_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def parse_post_json(raw: str) -> dict:
    """Extract the JSON object from an LLM response, tolerating code fences or
    surrounding prose. Raises ValueError if no valid object/required keys."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text[:4].lower() == "json" else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in LLM output")
    data = json.loads(text[start : end + 1])
    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"LLM output missing keys: {missing}")
    return data


class GeneratorService:
    def __init__(
        self,
        topic_repo: TopicRepository,
        article_repo: ArticleRepository,
        style_repo: StyleProfileRepository,
        post_repo: PostRepository,
        *,
        llm: LLMClient | None = None,
        rag: ChromaRAG | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.topic_repo = topic_repo
        self.article_repo = article_repo
        self.style_repo = style_repo
        self.post_repo = post_repo
        self.settings = settings or get_settings()
        self.llm = llm or OllamaClient(self.settings)
        self.rag = rag or ChromaRAG(settings=self.settings)

    async def generate(self, topic_id: int, *, style_name: str = "default") -> GeneratedPost:
        topic = self.topic_repo.get(topic_id)
        if topic is None:
            raise TopicNotFound(f"topic {topic_id} not found")

        trend_score = max((t.score for t in topic.trends), default=0.0)
        style = self.style_repo.get_by_name(style_name)
        style_features = style.features if style else {}

        facts = self._grounding(topic)
        prompt = self._build_prompt(topic, trend_score, style_features, facts)

        raw = await self.llm.generate(prompt, json_mode=True)
        data = parse_post_json(raw)

        post = GeneratedPost(
            topic_id=topic.id,
            style_id=style.id if style else None,
            headline=str(data.get("headline", ""))[:512],
            hook=str(data.get("hook", "")),
            body=str(data["body"]),
            cta=str(data.get("cta", "")),
            hashtags=self._clean_hashtags(data.get("hashtags", [])),
            reason=str(data.get("topic_reason", "")) or None,
            trend_score=trend_score,
            status=PostStatus.DRAFT,
        )
        self.post_repo.create(post)
        self.post_repo.db.commit()
        logger.info("Generated DRAFT post %s for topic %s", post.id, topic.id)
        return post

    # --- internals -----------------------------------------------------------

    def _grounding(self, topic: Topic) -> list[GroundingFact]:
        try:
            facts = self.rag.query(topic.name, k=self.settings.rag_top_k)
        except Exception:  # RAG store missing/empty — fall back to topic members
            logger.warning("RAG query failed; falling back to topic articles", exc_info=True)
            facts = []
        if facts:
            return facts
        return [
            GroundingFact(title=a.title, source=a.source, url=a.url)
            for a in topic.articles[: self.settings.rag_top_k]
        ]

    def _build_prompt(
        self, topic: Topic, trend_score: float, style: dict, facts: list[GroundingFact]
    ) -> str:
        fact_lines = "\n".join(f"- [{f.source}] {f.title} ({f.url})" for f in facts) or "(none)"
        return _load_template(str(_PROMPT_PATH)).format(
            topic=topic.name,
            trend_score=round(trend_score, 3),
            style=json.dumps(style, ensure_ascii=False),
            brand_rules=self.settings.brand_rules,
            facts=fact_lines,
        )

    @staticmethod
    def _clean_hashtags(value) -> list[str]:
        if not isinstance(value, list):
            return []
        out = []
        for tag in value[:8]:
            tag = str(tag).lstrip("#").strip()
            if tag:
                out.append(tag)
        return out
