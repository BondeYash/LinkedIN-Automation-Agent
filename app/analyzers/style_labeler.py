"""Descriptive style labels — the LLM half of style learning.

The analyzer asks a labeler for *short categorical labels* (hook style, CTA
style, storytelling pattern, tone) — never copied sentences. The LLM-backed
labeler arrives in Phase 5 (Ollama); until then `NullStyleLabeler` returns an
empty mapping so the numeric profile still builds and saves.

Keeping this behind a Protocol means Phase 5 swaps in the real labeler without
touching the analyzer.
"""

from __future__ import annotations

from typing import Protocol


class StyleLabeler(Protocol):
    async def label(self, texts: list[str]) -> dict: ...


class NullStyleLabeler:
    """No-op labeler used until the LLM client lands (Phase 5)."""

    async def label(self, texts: list[str]) -> dict:
        return {}
