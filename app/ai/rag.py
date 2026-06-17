"""Retrieval-Augmented Generation store over ChromaDB.

Holds article embeddings so the generator can pull the top-K most relevant
articles for a topic and paste them into the prompt as grounding facts (keeps
posts truthful and current). Phase 6 reuses the same store for dedup.

Embeddings come from our own `Embedder` (sentence-transformers) — passed in
explicitly so Chroma never downloads its own default model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.embeddings import Embedder, get_embedder
from app.core.config import Settings, get_settings
from app.models.models import Article

logger = logging.getLogger(__name__)


@dataclass
class GroundingFact:
    title: str
    source: str
    url: str


class ChromaRAG:
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
            # cosine space matches our normalized embeddings.
            self._collection = client.get_or_create_collection(
                name=self.settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @staticmethod
    def _doc(article: Article) -> str:
        return f"{article.title}. {(article.content or '')[:500]}".strip()

    def index(self, articles: list[Article]) -> int:
        """Upsert articles into the vector store. Returns count indexed."""
        rows = [a for a in articles if a.id is not None]
        if not rows:
            return 0
        embeddings = self.embedder.embed([self._doc(a) for a in rows])
        self._coll().upsert(
            ids=[str(a.id) for a in rows],
            embeddings=[e.tolist() for e in embeddings],
            documents=[self._doc(a) for a in rows],
            metadatas=[
                {"title": a.title, "source": a.source, "url": a.url} for a in rows
            ],
        )
        logger.info("RAG indexed %d articles", len(rows))
        return len(rows)

    def query(self, text: str, *, k: int = 5) -> list[GroundingFact]:
        """Top-K most relevant indexed articles for `text`."""
        coll = self._coll()
        if coll.count() == 0:
            return []
        vector = self.embedder.embed([text])[0].tolist()
        res = coll.query(query_embeddings=[vector], n_results=min(k, coll.count()))
        metas = (res.get("metadatas") or [[]])[0]
        return [
            GroundingFact(
                title=m.get("title", ""), source=m.get("source", ""), url=m.get("url", "")
            )
            for m in metas
        ]
