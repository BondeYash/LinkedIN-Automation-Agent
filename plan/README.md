# Build Plan — Index & Global Setup

This folder has one plan file per module. Build in order. Each file is self-contained: what to install, what to create, how to test, when you are done.

> **Read this README fully first.** It sets up the Python environment and rules every other plan file assumes.

---

## How to read each plan file

Every file follows the same shape, so it is easy to follow:

1. **Goal** — what this module does, in plain words.
2. **Depends on** — which earlier phases must be finished first.
3. **Install** — exact `pip install` commands for this module only.
4. **Build steps** — small numbered steps, in order.
5. **Files you create** — what new files appear after this phase.
6. **Test it** — how to check the module works before moving on.
7. **Done checklist** — tick boxes; all ticked = move to next file.

---

## Build order

| # | File | Module | Build after |
|---|------|--------|-------------|
| 0 | `00-foundation.md` | Project skeleton, config, logging, Docker | — |
| 1 | `01-persistence.md` | Database models, migrations, repositories | 0 |
| 2 | `02-collectors.md` | News collectors (RSS, HN, GitHub, Dev.to, Reddit) | 1 |
| 3 | `03-trend-analyzer.md` | Trend scoring + topic clustering | 2 |
| 4 | `04-style-intelligence.md` | Learn writing style from past posts | 1 |
| 5 | `05-ai-generator.md` | Ollama post generation + RAG | 3, 4 |
| 6 | `06-quality-gates.md` | Duplicate detection + fact-check | 5 |
| 7 | `07-approval-system.md` | Dashboard, email, Teams, Sheets, JWT auth | 6 |
| 8 | `08-publisher.md` | Publish to LinkedIn + retry | 7 |
| 9 | `09-analytics.md` | Pull engagement + weekly report | 8 |
| 10 | `10-engagement-coach.md` | Audit your account + improvement tips | 9 |
| 11 | `11-scheduler-api-tests.md` | Daily scheduler, full REST, tests, README | all |

---

## Global environment setup (do this once, before Phase 0)

We keep all Python packages inside a **virtual environment (venv)**. A venv is a private box of packages just for this project, so it never clashes with other projects or your system Python.

### Step 1 — Check Python version
Need Python 3.12 or newer.
```bash
python3 --version
```
If older, install Python 3.12 first (use `pyenv` or your OS package manager).

### Step 2 — Create the project folder and go into it
```bash
cd ~/Documents/Linked-In-Agent
```

### Step 3 — Create the virtual environment
```bash
python3 -m venv venv
```
This makes a `venv/` folder holding the private Python.

### Step 4 — Activate it
```bash
source venv/bin/activate
```
Your shell prompt now shows `(venv)`. **Every time** you open a new terminal to work on this project, run this activate line again.

To leave the venv later:
```bash
deactivate
```

### Step 5 — Upgrade pip (the installer)
```bash
pip install --upgrade pip
```

### Step 6 — How we track packages
Every plan file tells you to install packages with `pip install ...`. After installing, always save the list so the project is reproducible:
```bash
pip freeze > requirements.txt
```
Anyone can later recreate the exact environment with:
```bash
pip install -r requirements.txt
```

### Step 7 — Keep secrets in `.env`
Never put passwords or API keys in code. They go in a file named `.env`. We also keep a safe template `.env.example` (no real secrets) in git. Add `.env` and `venv/` to `.gitignore` so they are never committed:
```
venv/
.env
__pycache__/
*.pyc
logs/
```

---

## Golden rules (apply to every phase)

- **Activate the venv** before any `pip` or `python` command.
- **Install only what the current phase needs** — keeps things clean.
- **Run `pip freeze > requirements.txt`** after each install.
- **Test the module** before starting the next file.
- **Commit** after each working phase, so you can always go back.
- **No secrets in code** — always `.env`.

Now open `00-foundation.md` and begin.
