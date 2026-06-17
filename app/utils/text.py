"""Small text/url helpers shared across collectors."""

from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def url_hash(url: str) -> str:
    """Stable sha256 of a URL — the level-1 dedup key.

    The URL is lower-cased and stripped of a trailing slash so trivial variants
    of the same link collapse to one hash.
    """
    normalized = url.strip().lower().rstrip("/")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def clean_text(value: str | None) -> str:
    """Collapse whitespace and trim. Returns '' for None."""
    if not value:
        return ""
    return _WS_RE.sub(" ", value).strip()
