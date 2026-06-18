"""Gate 2 — fact verification.

Splits a draft into individual claims, pulls the most relevant indexed articles
for each claim (RAG), then asks the LLM in a single batched call whether each
claim is supported by its sources. Any unsupported claim flags the post for human
review — the model is never trusted to publish unbacked statements.

One LLM call per post (not per claim) keeps latency bounded on a CPU-only box.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.ai.ollama_client import LLMClient, get_llm_client
from app.ai.rag import ChromaRAG, GroundingFact
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "factcheck.txt"
# Split body into sentence-ish claims on sentence terminators and newlines.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class ClaimCheck:
    claim: str
    supported: bool
    source: str | None = None


@dataclass
class FactVerdict:
    checks: list[ClaimCheck] = field(default_factory=list)

    @property
    def unsupported(self) -> list[ClaimCheck]:
        return [c for c in self.checks if not c.supported]

    @property
    def all_supported(self) -> bool:
        return not self.unsupported


def split_claims(body: str, *, min_chars: int, max_claims: int) -> list[str]:
    """Break post body into candidate factual claims. Drops short fluff lines
    (hooks, CTAs, one-word punches) that carry no verifiable fact."""
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(body or "")]
    claims = [p for p in parts if len(p) >= min_chars]
    return claims[:max_claims]


class FactChecker:
    def __init__(
        self,
        *,
        rag: ChromaRAG | None = None,
        llm: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.rag = rag or ChromaRAG(settings=self.settings)
        self.llm = llm or get_llm_client(self.settings)

    async def check(self, body: str) -> FactVerdict:
        claims = split_claims(
            body,
            min_chars=self.settings.factcheck_min_claim_chars,
            max_claims=self.settings.factcheck_max_claims,
        )
        if not claims:
            return FactVerdict(checks=[])

        # Gather candidate sources per claim from the article RAG store.
        sources: list[list[GroundingFact]] = []
        for claim in claims:
            try:
                sources.append(self.rag.query(claim, k=self.settings.factcheck_rag_k))
            except Exception:  # store missing/empty — no sources for this claim
                logger.warning("Fact-check RAG query failed", exc_info=True)
                sources.append([])

        prompt = self._build_prompt(claims, sources)
        raw = await self.llm.generate(prompt, json_mode=True)
        verdicts = self._parse(raw, len(claims))

        checks = [
            ClaimCheck(
                claim=claim,
                supported=verdicts.get(i, False),
                source=(sources[i][0].source if sources[i] else None),
            )
            for i, claim in enumerate(claims)
        ]
        return FactVerdict(checks=checks)

    # --- internals -----------------------------------------------------------

    def _build_prompt(self, claims: list[str], sources: list[list[GroundingFact]]) -> str:
        blocks = []
        for i, claim in enumerate(claims):
            facts = "\n".join(f"  - [{f.source}] {f.title}" for f in sources[i]) or "  - (no sources found)"
            blocks.append(f"CLAIM {i}: {claim}\nSOURCES:\n{facts}")
        template = _PROMPT_PATH.read_text(encoding="utf-8")
        return template.format(claims_block="\n\n".join(blocks))

    @staticmethod
    def _parse(raw: str, n: int) -> dict[int, bool]:
        """Parse the LLM's JSON verdict into {claim_index: supported}. Anything
        unparseable or missing defaults to unsupported (fail closed)."""
        try:
            text = raw[raw.find("{") : raw.rfind("}") + 1]
            data = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            logger.warning("Fact-check output not JSON; failing all claims closed")
            return {}
        out: dict[int, bool] = {}
        for item in data.get("claims", []):
            try:
                idx = int(item["index"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= idx < n:
                out[idx] = bool(item.get("supported", False))
        return out
