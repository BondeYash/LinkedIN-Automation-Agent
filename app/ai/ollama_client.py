"""Thin async wrapper around a local Ollama server.

The rest of the app depends on the `LLMClient` Protocol, never on `ollama`
directly — so a fake client drives the tests and a different backend could be
swapped in without touching the generator.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.core.config import Settings, get_settings
from app.utils.http import transient_retry

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    async def generate(self, prompt: str, *, json_mode: bool = False) -> str: ...


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the configured LLM backend. `LLM_BACKEND=groq` returns a GroqClient
    (free hosted API, no card); anything else falls back to local Ollama. Services
    call this instead of hard-coding a client, so the backend is one env switch."""
    settings = settings or get_settings()
    if settings.llm_backend.lower() == "groq":
        from app.ai.groq_client import GroqClient

        return GroqClient(settings)
    return OllamaClient(settings)


class OllamaClient:
    """Calls a local Ollama model. `json_mode=True` asks Ollama to constrain the
    output to valid JSON (its native `format="json"`)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from ollama import AsyncClient

            self._client = AsyncClient(
                host=self.settings.ollama_host,
                timeout=self.settings.ollama_timeout_seconds,
            )
        return self._client

    @transient_retry
    async def generate(self, prompt: str, *, json_mode: bool = False) -> str:
        client = self._ensure_client()
        options = {
            "temperature": self.settings.ollama_temperature,
            "num_predict": self.settings.ollama_num_predict,
        }
        # Pin all cores when configured; 0 leaves it to Ollama's autodetect.
        if self.settings.ollama_num_thread > 0:
            options["num_thread"] = self.settings.ollama_num_thread
        response = await client.generate(
            model=self.settings.ollama_model,
            prompt=prompt,
            format="json" if json_mode else "",
            options=options,
            keep_alive=self.settings.ollama_keep_alive,
        )
        return response.get("response", "")
