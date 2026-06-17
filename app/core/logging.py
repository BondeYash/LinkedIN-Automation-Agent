"""Centralised logging setup.

One `setup_logging()` call at startup configures the root logger with:
- a rotating file handler (`logs/app.log`, 10 MB x 5 backups), and
- a console handler.

Every module then just does `logging.getLogger(__name__)` and inherits this
configuration. Calling `setup_logging()` more than once is safe (idempotent).
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.core.config import get_settings

_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "app.log"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configured = False


def setup_logging() -> None:
    """Configure the root logger. Idempotent — safe to call repeatedly."""

    global _configured
    if _configured:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Replace any handlers a prior import (e.g. uvicorn) installed.
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True
    logging.getLogger(__name__).info(
        "Logging configured (level=%s, file=%s)", settings.log_level, _LOG_FILE
    )
