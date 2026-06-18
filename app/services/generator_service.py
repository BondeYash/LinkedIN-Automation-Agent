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

from app.ai.dedup import PostDedup
from app.ai.factcheck import FactChecker
from app.ai.ollama_client import LLMClient, get_llm_client
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

_AI_DIR = Path(__file__).resolve().parent.parent / "ai" / "prompts"
_PROMPT_PATH = _AI_DIR / "generation.txt"
_REGEN_PATH = _AI_DIR / "regeneration.txt"
_OPT_PATH = _AI_DIR / "optimization.txt"  # auto-tuned by the Phase 9 feedback loop
_REQUIRED_KEYS = ("headline", "hook", "body", "cta", "hashtags")


class TopicNotFound(LookupError):
    pass


@lru_cache(maxsize=4)
def _load_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _load_optimization() -> str:
    """Read the auto-tuned hints fresh each call (the feedback loop rewrites the
    file between generations). Missing file → a neutral placeholder."""
    try:
        return _OPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "(none yet)"


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
        dedup: PostDedup | None = None,
        factcheck: FactChecker | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.topic_repo = topic_repo
        self.article_repo = article_repo
        self.style_repo = style_repo
        self.post_repo = post_repo
        self.settings = settings or get_settings()
        self.llm = llm or get_llm_client(self.settings)
        self.rag = rag or ChromaRAG(settings=self.settings)
        # Quality gates (Phase 6). Default None → skipped, so the generator works
        # standalone and unit tests drive it without a vector store. The API wires
        # in real gates.
        self.dedup = dedup
        self.factcheck = factcheck

    async def generate(self, topic_id: int, *, style_name: str = "default") -> GeneratedPost:
        topic = self.topic_repo.get(topic_id)
        if topic is None:
            raise TopicNotFound(f"topic {topic_id} not found")

        trend_score = max((t.score for t in topic.trends), default=0.0)
        style = self.style_repo.get_by_name(style_name)
        style_features = style.features if style else {}
        facts = self._grounding(topic)

        # --- Generate, with Gate 1 (dedup) regeneration loop -----------------
        data = await self._produce(topic, trend_score, style_features, facts)
        review: dict = {}
        if self.dedup is not None:
            data, dup = await self._dedup_loop(topic, trend_score, style_features, facts, data)
            if dup.is_duplicate:
                review["duplicate"] = {
                    "score": dup.score,
                    "matched_post_id": dup.matched_post_id,
                    "tries": self.settings.dedup_max_regen_tries,
                }

        # --- Gate 2 (fact check) ---------------------------------------------
        if self.factcheck is not None:
            verdict = await self.factcheck.check(str(data["body"]))
            if not verdict.all_supported:
                review["unsupported_claims"] = [c.claim for c in verdict.unsupported]

        status = PostStatus.NEEDS_REVIEW if review else PostStatus.DRAFT
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
            review_notes=review or None,
            status=status,
        )
        self.post_repo.create(post)
        self.post_repo.db.commit()

        # Register accepted (non-duplicate) posts so future drafts dedup against them.
        if self.dedup is not None and "duplicate" not in review:
            try:
                self.dedup.add(str(post.id), self._dedup_text(data))
            except Exception:  # indexing must never fail the request
                logger.warning("Dedup indexing failed for post %s", post.id, exc_info=True)

        logger.info("Generated %s post %s for topic %s", status.value, post.id, topic.id)
        return post

    # --- internals -----------------------------------------------------------

    async def _produce(
        self, topic: Topic, trend_score: float, style: dict, facts, *, extra: str = ""
    ) -> dict:
        """One LLM round-trip: build prompt → call model → parse JSON."""
        prompt = self._build_prompt(topic, trend_score, style, facts) + extra
        raw = await self.llm.generate(prompt, json_mode=True)
        return parse_post_json(raw)

    async def _dedup_loop(self, topic, trend_score, style, facts, data):
        """Regenerate while the draft is too similar to a past post, capped at
        `dedup_max_regen_tries`. Returns the final (data, verdict)."""
        dup = self.dedup.check(self._dedup_text(data))
        tries = 0
        while dup.is_duplicate and tries < self.settings.dedup_max_regen_tries:
            tries += 1
            logger.info(
                "Draft too similar (%.3f) to post %s — regenerating (%d/%d)",
                dup.score, dup.matched_post_id, tries, self.settings.dedup_max_regen_tries,
            )
            extra = _REGEN_PATH.read_text(encoding="utf-8").format(similarity=dup.score)
            data = await self._produce(topic, trend_score, style, facts, extra=extra)
            dup = self.dedup.check(self._dedup_text(data))
        return data, dup

    @staticmethod
    def _dedup_text(data: dict) -> str:
        """Text representation compared/stored for duplicate detection."""
        return f"{data.get('headline', '')}\n{data.get('body', '')}".strip()

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
            optimization=_load_optimization(),
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
