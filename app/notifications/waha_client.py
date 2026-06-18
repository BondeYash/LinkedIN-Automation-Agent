"""Thin WAHA (WhatsApp HTTP API) client.

One job: send a plain-text WhatsApp message through a running WAHA server
(https://waha.devlike.pro). Auth is the `X-Api-Key` header. The session must be
authenticated once by scanning a QR code — see `scripts/whatsapp_setup.py`.

Both the approval notifier and the weekly-report job send through here, so the
transport (base url, api key, session, recipient) lives in exactly one place.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class WahaNotConfigured(RuntimeError):
    """WAHA api key or recipient is missing."""


def is_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.waha_api_key and settings.whatsapp_recipient)


def send_text(
    text: str,
    *,
    chat_id: str | None = None,
    settings: Settings | None = None,
) -> dict:
    """Send a WhatsApp text via WAHA. Returns the WAHA response JSON.

    Raises `WahaNotConfigured` if unconfigured, or `httpx.HTTPStatusError` on a
    non-2xx response so callers can record a FAILED notification.
    """
    settings = settings or get_settings()
    if not is_configured(settings):
        raise WahaNotConfigured("waha_api_key / whatsapp_recipient not set")
    url = f"{settings.waha_base_url.rstrip('/')}/api/sendText"
    body = {
        "session": settings.waha_session,
        "chatId": chat_id or settings.whatsapp_recipient,
        "text": text,
    }
    resp = httpx.post(
        url,
        json=body,
        headers={"X-Api-Key": settings.waha_api_key},
        timeout=settings.waha_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else {}
