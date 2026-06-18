"""Trending-hashtag suggestions to boost reach (Phase 13).

LinkedIn reach leans heavily on a smart hashtag mix: a few broad high-volume tags
(discovery), a few niche tags (relevance), and whatever is *trending right now*.
This service assembles that mix from three signals and hands the generator a
ranked shortlist to weave into each post:

1. LIVE TREND tags — derived from the topics currently ranking on our trend index
   (genuinely "trending" because they come from today's news/clusters).
2. PROVEN tags — hashtags that correlated with high engagement on our own past
   posts (from the analytics feedback loop).
3. EVERGREEN tags — a curated high-volume tech/leadership set so a post is never
   left with too few tags.

The generator stays in control: these are *suggestions* injected into the prompt,
not a hard list, so the model still picks what fits the specific post.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.repositories.repos import PostRepository, TrendRepository

logger = logging.getLogger(__name__)

# Broad, high-volume tech / leadership tags — the discovery layer. Kept evergreen
# so reach never collapses when trend/analytics signals are thin (cold start).
EVERGREEN: tuple[str, ...] = (
    "AI",
    "ArtificialIntelligence",
    "MachineLearning",
    "SoftwareEngineering",
    "TechLeadership",
    "Innovation",
    "FutureOfWork",
    "DataScience",
    "CloudComputing",
    "DevOps",
    "DigitalTransformation",
    "ProductManagement",
    "Startups",
    "Technology",
    "Programming",
)

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]+")
# Skip junk topic tokens (version numbers, handles, common stopwords).
_STOP = {"the", "and", "for", "with", "your", "you", "release", "released", "new", "has", "have"}


def _to_hashtag(text: str) -> str | None:
    """Turn a SHORT topic phrase into a single CamelCase hashtag, or None if it's
    unusable (a bare handle like 'rebel0789/codexpro') or clearly a headline
    rather than a tag. Headlines make terrible hashtags, so anything with more
    than 4 meaningful words is rejected — evergreen/proven tags fill instead."""
    words = [w for w in _WORD.findall(text) if w.lower() not in _STOP and not w.isdigit()]
    words = [w for w in words if 2 <= len(w) <= 20]
    if not words or len(words) > 4:
        return None
    return "".join(w[:1].upper() + w[1:] for w in words[:3])


class HashtagService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.trends = TrendRepository(db)
        self.posts = PostRepository(db)

    def suggest(self, topic_name: str, *, limit: int = 10) -> list[str]:
        """Ranked, de-duplicated hashtag shortlist for a post on `topic_name`.
        Order = topic-specific → live-trend → proven → evergreen, so the most
        relevant tags lead and evergreen only fills the tail."""
        ranked: list[str] = []
        seen: set[str] = set()

        def push(raw: str | None) -> None:
            # Every source funnels through _to_hashtag, so a multi-word or punctuated
            # value ('AI-generated content', a handle) is either cleaned to a single
            # CamelCase token or dropped — no spaces/junk ever reach the prompt.
            tag = _to_hashtag(raw or "")
            if not tag:
                return
            key = tag.lower()
            if key not in seen:
                seen.add(key)
                ranked.append(tag)

        # 1. The post's own topic first (most relevant).
        push(topic_name)

        # 2. Live trending topics from the current trend index.
        try:
            for t in self.trends.top_recent(limit=8):
                push(t.topic.name if t.topic else "")
        except Exception:  # never let suggestion failure break generation
            logger.warning("trend hashtag lookup failed", exc_info=True)

        # 3. Proven performers from our own published posts' tags.
        try:
            for tag in self._proven_tags():
                push(tag)
        except Exception:
            logger.warning("proven hashtag lookup failed", exc_info=True)

        # 4. Evergreen fill.
        for tag in EVERGREEN:
            push(tag)

        return ranked[:limit]

    def _proven_tags(self, *, scan: int = 50) -> list[str]:
        """Hashtags seen most often on recent published/approved posts — a cheap
        proxy for 'what we've leaned on that performed', no heavy report build."""
        from collections import Counter

        from app.models.enums import PostStatus

        counts: Counter[str] = Counter()
        for status in (PostStatus.PUBLISHED, PostStatus.APPROVED):
            for post in self.posts.by_status(status, limit=scan):
                for tag in post.hashtags or []:
                    cleaned = str(tag).lstrip("#").strip()
                    if cleaned:
                        counts[cleaned] += 1
        return [tag for tag, _ in counts.most_common(8)]
