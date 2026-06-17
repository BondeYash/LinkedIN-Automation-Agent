"""Password hashing helpers.

Uses the `bcrypt` library directly (passlib 1.7.x is unmaintained and breaks
with bcrypt >= 4). bcrypt only considers the first 72 bytes of a password;
that is an industry-standard limit and fine for our use.

Minimal in Phase 1 (seed needs to store a hashed admin password). Phase 7
extends this module with JWT create/decode for login.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import Settings, get_settings


class TokenError(Exception):
    """Raised when a JWT is missing, expired, malformed, or the wrong type."""


def hash_password(plain: str) -> str:
    """Return a salted bcrypt hash of `plain` (as a utf-8 string)."""
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# --- JWT (Phase 7) ----------------------------------------------------------


def _encode(claims: dict, *, minutes: int, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {**claims, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _decode(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:  # expired, bad signature, malformed
        raise TokenError(str(exc)) from exc


def create_access_token(*, user_id: int, role: str, settings: Settings | None = None) -> str:
    """Login token. `sub` is the user id; `role` drives authorization."""
    settings = settings or get_settings()
    return _encode(
        {"sub": str(user_id), "role": role, "type": "access"},
        minutes=settings.access_token_expire_minutes,
        settings=settings,
    )


def decode_access_token(token: str, settings: Settings | None = None) -> dict:
    """Return the claims of a valid access token. Raises `TokenError` otherwise."""
    settings = settings or get_settings()
    claims = _decode(token, settings)
    if claims.get("type") != "access":
        raise TokenError("not an access token")
    return claims


def create_action_token(
    *, post_id: int, action: str, settings: Settings | None = None
) -> str:
    """Signed, expiring token for a one-click approve/reject/regenerate link sent
    in a notification — so only someone holding the link can act, no login UI."""
    settings = settings or get_settings()
    return _encode(
        {"post_id": post_id, "action": action, "type": "action"},
        minutes=settings.action_token_expire_minutes,
        settings=settings,
    )


def decode_action_token(token: str, settings: Settings | None = None) -> dict:
    """Validate a one-click action token. Raises `TokenError` if invalid."""
    settings = settings or get_settings()
    claims = _decode(token, settings)
    if claims.get("type") != "action":
        raise TokenError("not an action token")
    return claims
