"""Descriptive style labels — the LLM half of style learning.

The analyzer asks a labeler for *short categorical labels* (hook style, CTA
style, storytelling pattern, tone) — never copied sentences. The LLM-backed
labeler arrives in Phase 5 (Ollama); until then `NullStyleLabeler` returns an
empty mapping so the numeric profile still builds and saves.

Keeping this behind a Protocol means Phase 5 swaps in the real labeler without
touching the analyzer.
"""

import json
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

_LABEL_PROMPT = (
    "Analyze the writing STYLE of these LinkedIn posts. Return STRICT JSON only "
    "with short categorical labels — never copied sentences — using exactly these "
    'keys: {{"hook_style": "...", "cta_style": "...", "storytelling": "...", '
    '"tone": "..."}}.\n\nPOSTS:\n{posts}'
)


class StyleLabeler(Protocol):
    async def label(self, texts: list[str]) -> dict: ...


class NullStyleLabeler:
    """No-op labeler — used when no LLM is configured."""

    async def label(self, texts: list[str]) -> dict:
        return {}


class OllamaStyleLabeler:
    """LLM-backed labeler: asks the model for short style labels (not content)."""

    def __init__(self, llm) -> None:
        self.llm = llm

    async def label(self, texts: list[str]) -> dict:
        joined = "\n\n---\n\n".join(texts[:10])
        prompt = _LABEL_PROMPT.format(posts=joined)
        try:
            raw = await self.llm.generate(prompt, json_mode=True)
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end == -1:
                return {}
            data = json.loads(raw[start : end + 1])
            # keep only short string labels, never long copied text
            return {
                k: v for k, v in data.items()
                if isinstance(v, str) and len(v) <= 80
            }
        except Exception:
            logger.warning("Style labeling failed; returning no labels", exc_info=True)
            return {}
