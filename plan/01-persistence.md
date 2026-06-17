# Phase 1 — Persistence (Database)

## Goal
Create all database tables as Python classes, set up migrations (versioned database changes), build repositories (the only place that touches the database), and load some starter data.

## Depends on
Phase 0.

## Install
```bash
pip install alembic
pip freeze > requirements.txt
```
- **alembic** — tracks database changes over time, like git for your tables. Lets you upgrade/rollback the schema safely.

## Build steps

1. **Write the ORM models** (`app/models/`). One file per group or one `models.py`. Create SQLAlchemy classes for every table from the architecture doc:
   `users, articles, topics, trends, style_profiles, generated_posts, approvals, publishing_history, analytics, embeddings, notifications, account_posts, engagement_insights, improvement_tips, audit_logs`.
   Add primary keys, foreign keys, unique constraints (e.g. `articles.url` unique), timestamps, and relationships. Not every table is used yet — that is fine; we create them all now so migrations are done once.

2. **Set up Alembic.**
   ```bash
   alembic init migrations
   ```
   Edit `alembic.ini` and `migrations/env.py` so Alembic reads the DB URL from settings and sees your models' `Base.metadata`.

3. **Create the first migration** (auto-generated from models):
   ```bash
   alembic revision --autogenerate -m "initial tables"
   ```
   Read the generated file to confirm it creates all tables, then apply it:
   ```bash
   alembic upgrade head
   ```

4. **Write a base repository** (`app/repositories/base.py`). A generic class with `get(id)`, `list()`, `create(obj)`, `update(obj)`, `delete(id)`. Other repos inherit from it.

5. **Write specific repositories** (`app/repositories/`). One per table you read/write a lot: `UserRepository`, `ArticleRepository`, `PostRepository`, `ApprovalRepository`, `TrendRepository`, etc. Add domain queries here, e.g. `ArticleRepository.get_by_url_hash()`, `ApprovalRepository.get_pending()`.

6. **Wire repositories into DI** (`app/api/deps.py`). Small provider functions that take `get_db()` and return a repository, so API routes just ask for the repo they need.

7. **Write seed data** (`seed/seed.py`). A script that inserts: one admin user (hashed password), a sample style profile, and the list of RSS/source URLs to collect from. Make it safe to run twice (skip if already there).

## Files you create
```
app/models/*.py
app/repositories/base.py
app/repositories/*.py
app/api/deps.py
migrations/...           (alembic)
seed/seed.py
```

## Test it
1. Make sure PostgreSQL is running (`docker-compose up postgres`).
2. Run `alembic upgrade head` — no errors.
3. Connect to the DB and list tables — all expected tables exist.
4. Run the seed script:
   ```bash
   python -m seed.seed
   ```
5. Query `users` — admin row exists. Run seed again — no duplicate, no crash.

## Done checklist
- [ ] All model classes written with keys + relationships
- [ ] Alembic set up, first migration applied
- [ ] All tables visible in the database
- [ ] Base + specific repositories work
- [ ] Seed script runs (and is safe to re-run)
- [ ] Committed to git

Next: `02-collectors.md`
