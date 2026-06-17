"""Password hashing helpers.

Uses the `bcrypt` library directly (passlib 1.7.x is unmaintained and breaks
with bcrypt >= 4). bcrypt only considers the first 72 bytes of a password;
that is an industry-standard limit and fine for our use.

Minimal in Phase 1 (seed needs to store a hashed admin password). Phase 7
extends this module with JWT create/decode for login.
"""

from __future__ import annotations

import bcrypt


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
