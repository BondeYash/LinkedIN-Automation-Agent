#!/usr/bin/env sh
# Container entrypoint: bring the DB schema up to date, then start the app.
#
# Migrations run here (not in a separate job) so a fresh volume or a new
# release is always schema-correct before uvicorn binds. The app runs as a
# SINGLE uvicorn process on purpose: the APScheduler cron lives in-process, and
# multiple workers would fire every job N times. Do not add --workers.
set -e

echo "[entrypoint] applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] starting uvicorn (single process — scheduler runs in-process)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
