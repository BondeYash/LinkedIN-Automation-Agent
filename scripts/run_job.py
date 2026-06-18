"""One-shot job runner for headless schedulers (GitHub Actions cron).

The in-process APScheduler is great when the app is long-running, but a powered-off
PC runs nothing. To make the cron PC-off-proof we run the SAME job bodies from a
short-lived process in the cloud:

    python scripts/run_job.py daily     # collect -> analyze -> generate -> notify
    python scripts/run_job.py weekly    # analytics sync + weekly report

Each opens its own DB session against DATABASE_URL (point it at a cloud Postgres
like Neon so state persists between runs). Exit code is non-zero on failure so the
workflow is marked red.
"""

from __future__ import annotations

import asyncio
import sys

from app.scheduler.scheduler import run_daily_pipeline, run_weekly_report


def main() -> int:
    job = (sys.argv[1] if len(sys.argv) > 1 else "daily").strip().lower()
    if job not in {"daily", "weekly"}:
        print(f"unknown job '{job}' (expected: daily | weekly)", file=sys.stderr)
        return 2

    runner = run_weekly_report if job == "weekly" else run_daily_pipeline
    result = asyncio.run(runner())
    print(f"[run_job] {job} done: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
