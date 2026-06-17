"""Thin async wrapper over the LinkedIn UGC Posts API.

Official API only — never scraping. One method, `create_post(text)`, posts a
PUBLIC text share for the configured member and returns the LinkedIn post id.
Retries are handled one layer up (the publisher), so this client just makes the
call and raises `httpx` errors verbatim for the retry policy to classify.

Auth: a member OAuth2 access token + the author URN, both from settings/.env.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_UGC_PATH = "/v2/ugcPosts"


class LinkedInAuthError(RuntimeError):
    """Publisher is missing its access token or author URN."""


class LinkedInClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def configured(self) -> bool:
        s = self.settings
        return bool(s.linkedin_access_token and s.linkedin_author_urn)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.linkedin_access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def _body(self, text: str) -> dict:
        """UGC share payload: a PUBLIC text-only post authored by the member."""
        return {
            "author": self.settings.linkedin_author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

    async def create_post(self, text: str) -> str:
        """Publish `text` and return the LinkedIn post id (the share URN).

        Raises `LinkedInAuthError` if credentials are missing, or `httpx`
        errors (TimeoutException / TransportError / HTTPStatusError) for the
        caller's retry policy to classify as transient or fatal.
        """
        if not self.configured():
            raise LinkedInAuthError(
                "LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN must be set to publish"
            )
        url = self.settings.linkedin_api_base.rstrip("/") + _UGC_PATH
        async with httpx.AsyncClient(timeout=self.settings.linkedin_timeout_seconds) as client:
            resp = await client.post(url, headers=self._headers(), json=self._body(text))
            resp.raise_for_status()  # 4xx/5xx -> HTTPStatusError
            # LinkedIn returns the new id in the body and the X-RestLi-Id header.
            post_id = resp.headers.get("x-restli-id") or resp.headers.get("X-RestLi-Id")
            if not post_id:
                try:
                    post_id = resp.json().get("id")
                except Exception:  # non-JSON body — fall through to the guard below
                    post_id = None
        if not post_id:
            raise httpx.HTTPError("LinkedIn accepted the post but returned no id")
        logger.info("Published to LinkedIn: %s", post_id)
        return str(post_id)
