# Phase 0 — Foundation

## Goal
Build the empty skeleton everything else sits on: folder layout, settings loader, logging, database connection, base classes (interfaces), and Docker. Nothing fancy yet — just a solid floor.

## Depends on
Nothing. This is first. (Do the **Global environment setup** in `README.md` first.)

## Install
```bash
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings python-dotenv sqlalchemy "psycopg[binary]"
pip freeze > requirements.txt
```
What these are, in plain words:
- **fastapi** — the web framework (gives us the API).
- **uvicorn** — the server that runs FastAPI.
- **pydantic** — checks data shapes; **pydantic-settings** loads `.env` safely.
- **python-dotenv** — reads the `.env` file.
- **sqlalchemy** — talks to the database with Python objects instead of raw SQL.
- **psycopg** — the PostgreSQL driver SQLAlchemy uses.

## Build steps

1. **Make the folder skeleton.** Create these empty folders, each with an empty `__init__.py` so Python treats them as packages:
   ```
   app/
     api/  core/  models/  schemas/  repositories/  services/
     collectors/  analyzers/  ai/  publishers/  notifications/
     scheduler/  database/  utils/
   tests/
   ```

2. **Write the settings loader** (`app/core/config.py`). Make a `Settings` class using `pydantic-settings`. It reads values from `.env`: database URL, app name, log level, secret key, Ollama host. Provide a single `get_settings()` function the rest of the app imports.

3. **Write logging setup** (`app/core/logging.py`). Configure Python's `logging` with a `RotatingFileHandler` (e.g. 10 MB per file, keep 5 backups) writing to `logs/app.log`, plus console output. One function `setup_logging()` called at startup.

4. **Write the database session** (`app/database/session.py`). Create the SQLAlchemy engine from the settings DB URL, a session factory, a `Base` for models, and a `get_db()` dependency that hands out a session and closes it after each request.

5. **Write base interfaces** (`app/core/base.py`). Abstract base classes (`ABC`): `BaseCollector` (`fetch()`), `BaseAnalyzer` (`analyze()`), `BaseNotifier` (`send()`), `BasePublisher` (`publish()`). These are contracts later modules fill in. This is what makes parts swappable.

6. **Write a tiny FastAPI app** (`app/main.py`). Create the `FastAPI()` object, call `setup_logging()`, and add one health route `GET /health` that returns `{"status": "ok"}`. This proves the server runs.

7. **Write `.env.example` and `.env`.** Put placeholder values in `.env.example` (commit it). Copy to `.env` with real values (never commit). Add `.env`, `venv/`, `logs/` to `.gitignore`.

8. **Write Docker files.**
   - `Dockerfile` — start from `python:3.12-slim`, copy code, install `requirements.txt`, run uvicorn.
   - `docker-compose.yml` — services: `app`, `postgres`, `ollama`, `chromadb`. Wire them with env vars and volumes.

## Files you create
```
app/main.py
app/core/config.py
app/core/logging.py
app/core/base.py
app/database/session.py
.env.example   .env   .gitignore
Dockerfile   docker-compose.yml
requirements.txt
```

## Test it
1. Activate venv.
2. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Open `http://localhost:8000/health` → should show `{"status":"ok"}`.
4. Open `http://localhost:8000/docs` → Swagger page loads.
5. Check `logs/app.log` exists and has a startup line.

## Done checklist
- [x] venv active, packages installed, `requirements.txt` saved
- [x] All folders exist with `__init__.py`
- [x] `/health` returns ok
- [x] Swagger `/docs` loads
- [x] Logs writing to file
- [x] `.env` ignored by git, `.env.example` committed
- [ ] `docker-compose up` starts app + postgres — files written; not yet launched (no Docker daemon run)
- [x] Committed to git

Next: `01-persistence.md`
