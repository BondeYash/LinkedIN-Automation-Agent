"""Shared HTTP retry policy for collectors.

Every external call is wrapped so a flaky network never crashes a collection
run: retry up to 3 times with exponential backoff, but only on transient errors
(timeouts, connection errors, 5xx, 429). 4xx client errors are not retried.
"""

from __future__ import annotations

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


def transient_retry(func):
    """Decorator: retry an async HTTP call on transient failures only."""

    return retry(
        retry=retry_if_exception(_is_transient),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )(func)
