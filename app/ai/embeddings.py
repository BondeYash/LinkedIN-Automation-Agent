"""Text embeddings — turn text into meaning-vectors for clustering and relevance.

The sentence-transformers model is loaded once (it's expensive: weights are read
from disk and the first run downloads them) and reused for the process lifetime.
Encoding is CPU-bound and blocking, so the async entrypoint offloads it to a
threadpool to avoid stalling the event loop.

Anything that needs vectors depends on the `Embedder` protocol, not the concrete
model, so tests can inject a cheap fake (see `tests/test_trend_scoring.py`).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Anything that turns a list of texts into an (n, d) float matrix whose rows
    are L2-normalized (so a dot product equals cosine similarity)."""

    def embed(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    """Embedder backed by a sentence-transformers model, loaded lazily once."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        # Double-checked locking: import + load only on first use, once.
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info("Loading embedding model %s", self.model_name)
                    self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,  # rows are unit vectors → dot = cosine
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Process-wide singleton embedder built from settings."""
    return SentenceTransformerEmbedder(get_settings().embedding_model)


async def embed_async(embedder: Embedder, texts: list[str]) -> np.ndarray:
    """Run a (blocking) embed call off the event loop."""
    return await asyncio.to_thread(embedder.embed, texts)
