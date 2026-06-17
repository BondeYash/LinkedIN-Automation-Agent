"""Style analyzer — turn sample posts into a reusable style profile.

Combines two sources of features:
  1. numeric stats from `style_features.aggregate` (lengths, emoji, hashtags…),
  2. descriptive labels from a `StyleLabeler` (hook/CTA/tone — LLM, Phase 5).

The result is one JSON document saved to `style_profiles`. It holds ONLY
aggregate numbers and short labels — never copied post text — so the generator
(Phase 5) can imitate the *style* without ever reproducing source content.
"""

from __future__ import annotations

import logging

from app.analyzers import style_features
from app.analyzers.style_labeler import NullStyleLabeler, StyleLabeler
from app.models.models import StyleProfile
from app.repositories.repos import StyleProfileRepository

logger = logging.getLogger(__name__)


class StyleAnalyzer:
    def __init__(
        self,
        style_repo: StyleProfileRepository,
        *,
        labeler: StyleLabeler | None = None,
    ) -> None:
        self.style_repo = style_repo
        self.labeler = labeler or NullStyleLabeler()

    async def build(
        self, texts: list[str], *, name: str, source: str | None = None
    ) -> StyleProfile:
        """Analyze `texts` and upsert a named style profile."""
        clean = [t for t in texts if t and t.strip()]
        if not clean:
            raise ValueError("no sample text provided")

        features = style_features.aggregate(clean)
        labels = await self.labeler.label(clean)
        if labels:
            features["labels"] = labels

        existing = self.style_repo.get_by_name(name)
        if existing is not None:
            existing.features = features
            existing.source = source or existing.source
            profile = self.style_repo.update(existing)
        else:
            profile = self.style_repo.create(
                StyleProfile(name=name, source=source, features=features)
            )

        self.style_repo.db.commit()
        logger.info(
            "Style profile '%s' built from %d posts (labels=%s)",
            name,
            features["sample_size"],
            bool(labels),
        )
        return profile
