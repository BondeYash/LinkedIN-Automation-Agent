"""Idempotent seed script.

Inserts starter data the app needs to boot usefully:
- one admin user (bcrypt-hashed password),
- a sample style profile.

Safe to run repeatedly — every insert is guarded by an existence check, so a
second run changes nothing and never crashes.

Run with:  python -m seed.seed
"""

from __future__ import annotations

import logging
import os

from app.core.logging import setup_logging
from app.database.session import SessionLocal
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.models import StyleProfile, User
from app.repositories.repos import StyleProfileRepository, UserRepository

logger = logging.getLogger(__name__)

ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "admin12345")
STYLE_NAME = "default"


def seed() -> None:
    setup_logging()
    db = SessionLocal()
    try:
        users = UserRepository(db)
        styles = StyleProfileRepository(db)

        # --- Admin user ------------------------------------------------------
        if users.get_by_email(ADMIN_EMAIL) is None:
            users.create(
                User(
                    email=ADMIN_EMAIL,
                    hashed_pw=hash_password(ADMIN_PASSWORD),
                    role=UserRole.ADMIN,
                )
            )
            logger.info("Seeded admin user %s", ADMIN_EMAIL)
        else:
            logger.info("Admin user %s already exists — skipping", ADMIN_EMAIL)

        # --- Sample style profile -------------------------------------------
        if styles.get_by_name(STYLE_NAME) is None:
            styles.create(
                StyleProfile(
                    name=STYLE_NAME,
                    source="seed",
                    features={
                        "tone": "insightful, concise",
                        "avg_length": 900,
                        "hook_style": "question-or-bold-claim",
                        "hashtag_count": 3,
                        "emoji": "sparing",
                    },
                )
            )
            logger.info("Seeded style profile '%s'", STYLE_NAME)
        else:
            logger.info("Style profile '%s' already exists — skipping", STYLE_NAME)

        db.commit()
        logger.info("Seed complete.")
    except Exception:
        db.rollback()
        logger.exception("Seed failed — rolled back")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
