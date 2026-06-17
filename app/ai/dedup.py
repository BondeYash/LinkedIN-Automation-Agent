"""Gate 1 — duplicate detection.

Stops the generator from re-publishing something too close to a post it already
made. New drafts are embedded and compared (cosine similarity) against a Chroma
collection of past accepted posts; anything above the threshold is "too similar"
and gets sent back for regeneration. Accepted posts are then added to the store
so future drafts are checked against them too.

Reuses the project's own sentence-transformers `Embedder` (same vectors as the
RAG store) — Chroma never loads its own model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.embeddings import Embedder, get_embedder
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class DedupVerdict:
    """Result of comparing a draft against the nearest past post."""

    is_duplicate: bool
    score: float  # cosine similarity 0–1 to the nearest post (0.0 if store empty)
    matched_post_id: str | None


class PostDedup:
    """Cosine-similarity duplicate check over a Chroma collection of past posts."""

    def __init__(
        self, *, embedder: Embedder | None = None, settings: Settings | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.embedder = embedder or get_embedder()
        self._collection = None

    def _coll(self):
        if self._collection is None:
            import chromadb

            client = chromadb.PersistentClient(path=self.settings.chroma_path)
            # cosine space matches our normalized embeddings: distance = 1 - cosine.
            self._collection = client.get_or_create_collection(
                name=self.settings.chroma_posts_collection,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def check(self, text: str) -> DedupVerdict:
        """Compare `text` to the nearest stored post. Empty store → not a dup."""
        coll = self._coll()
        if coll.count() == 0:
            return DedupVerdict(is_duplicate=False, score=0.0, matched_post_id=None)
        vector = self.embedder.embed([text])[0].tolist()
        res = coll.query(query_embeddings=[vector], n_results=1)
        distances = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        if not distances:
            return DedupVerdict(is_duplicate=False, score=0.0, matched_post_id=None)
        # Chroma cosine distance is 1 - cosine_similarity for normalized vectors.
        similarity = max(0.0, min(1.0, 1.0 - float(distances[0])))
        return DedupVerdict(
            is_duplicate=similarity >= self.settings.dedup_similarity_threshold,
            score=round(similarity, 4),
            matched_post_id=ids[0] if ids else None,
        )

    def add(self, post_id: str, text: str) -> None:
        """Register an accepted post so future drafts are checked against it."""
        vector = self.embedder.embed([text])[0].tolist()
        self._coll().upsert(
            ids=[str(post_id)],
            embeddings=[vector],
            documents=[text[:2000]],
        )
        logger.info("Dedup store indexed post %s", post_id)
