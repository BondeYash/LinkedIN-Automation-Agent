# Phase 11 — Scheduler, Full REST Surface, Tests & README

## Goal
Wire the whole pipeline to run automatically every morning, finalize the complete REST API, add integration tests across the flow, and write the project README. This is the "tie it all together" phase.

## Depends on
All earlier phases (0–10).

## Install
```bash
pip install apscheduler pytest pytest-asyncio httpx
pip freeze > requirements.txt
```
- **apscheduler** — schedule the daily pipeline.
- **pytest + pytest-asyncio** — test sync and async code.
- **httpx** — its `ASGITransport` test client hits the FastAPI app in-process.

## Build steps

### Scheduler
1. **Daily pipeline** (`scheduler/pipeline.py`): one `async def daily_pipeline()` that chains the modules in order — collect → trend → style → generate → quality gates → create draft → set `PENDING` → fire notifications. Each step logged; one failing step is caught and logged, does not kill the whole run.
2. **Scheduler wiring** (`scheduler/jobs.py`): APScheduler `AsyncIOScheduler`, register `daily_pipeline` at **07:00**. Also register `analytics_sync` (Phase 9) on a daily/weekly cadence. Start the scheduler in the FastAPI `lifespan` startup, shut it down cleanly on exit.
3. **Manual trigger:** `POST /admin/scheduler/run` to fire `daily_pipeline()` on demand (so you don't wait until 7am to test).

### Finalize REST surface
4. Confirm every route from the architecture exists and is wired:
   ```
   collectors/trends/topics  · generate  · approvals (+actions)
   publish/{id}              · analytics · coach/*
   admin/health|logs|scheduler · auth/login · history · search
   ```
5. **Health + ops** (`api/admin.py`): `GET /admin/health` (db + scheduler + ollama reachable), `GET /admin/logs`, `GET /admin/scheduler` (next run times).

### Tests
6. **Integration tests** (`tests/`): use the httpx ASGI client against a test DB.
   - Pipeline produces a draft and sets it `PENDING`.
   - Approval flow: login → list → approve → status `APPROVED`.
   - Publish guard: non-`APPROVED` post is rejected.
   - Analytics sync writes time-series rows.
   - Coach sync tags provenance.
   - Each collector parses a saved sample feed (no live network in tests — mock/fixture).
7. **Run:** `pytest -q` green before done.

### README
8. **`README.md`** at project root: what the system does, the architecture diagram, setup (venv, `.env`, migrations), how to run (`uvicorn`), how the daily flow works, and the API map.

## Files you create
```
scheduler/pipeline.py
scheduler/jobs.py
tests/conftest.py
tests/test_pipeline.py
tests/test_approval.py
tests/test_publish_guard.py
tests/test_analytics.py
tests/test_coach.py
README.md
```

## Test it
1. `POST /admin/scheduler/run` → full pipeline runs, a `PENDING` draft appears, notifications fire.
2. `GET /admin/scheduler` → shows next 07:00 run.
3. `GET /admin/health` → all green.
4. `pytest -q` → all tests pass.
5. Fresh clone + README steps → app boots from scratch.

## Done checklist
- [ ] `daily_pipeline` chains all modules, per-step error isolation
- [ ] APScheduler runs it at 07:00, starts/stops with the app
- [ ] Manual trigger endpoint works
- [ ] Every architecture route present + health/logs/scheduler ops
- [ ] Integration tests cover pipeline, approval, publish guard, analytics, coach
- [ ] `pytest -q` green
- [ ] Root README complete (setup → run → API map)
- [ ] Committed to git

Done — the full system is built. 🎉
