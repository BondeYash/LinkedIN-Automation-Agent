"""Groq backend for the `LLMClient` Protocol.

Groq serves Llama models over an OpenAI-compatible HTTP API on a generous free
tier (no credit card). It implements the same `generate(prompt, *, json_mode)`
contract as `OllamaClient`, so the generator / fact-checker / style-labeler swap
to it with no other code changes — only `LLM_BACKEND=groq` in the env.

`json_mode=True` uses Groq's native JSON object response_format. Note: like
OpenAI, Groq requires the word "JSON" to appear somewhere in the prompt when that
mode is on; every json_mode prompt in this app already instructs JSON output.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings, get_settings
from app.utils.http import transient_retry

logger = logging.getLogger(__name__)


class GroqNotConfigured(RuntimeError):
    """Raised when LLM_BACKEND=groq but no GROQ_API_KEY is set."""


class GroqClient:
    """Calls Groq's OpenAI-compatible chat-completions endpoint."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @transient_retry
    async def generate(self, prompt: str, *, json_mode: bool = False) -> str:
        s = self.settings
        if not s.groq_api_key:
            raise GroqNotConfigured(
                "GROQ_API_KEY is empty but LLM_BACKEND=groq. Set GROQ_API_KEY in .env."
            )

        payload: dict = {
            "model": s.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": s.groq_temperature,
            "max_tokens": s.groq_num_predict,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=s.groq_timeout_seconds) as client:
            resp = await client.post(
                f"{s.groq_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return data["choices"][0]["message"].get("content", "") or ""
