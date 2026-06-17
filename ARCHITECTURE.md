# LinkedIn Thought-Leadership Automation — System & Architecture

> AI-powered backend that discovers tech trends, generates original LinkedIn posts, routes them through **human approval**, publishes via official API, and learns from engagement. Human-in-the-loop is mandatory — nothing auto-publishes.

---

## 1. High-Level Overview

```
                          ┌─────────────────────────────────────────────┐
                          │            APScheduler (daily 07:00)          │
                          └───────────────────────┬─────────────────────┘
                                                  │ triggers pipeline
                                                  ▼
  ┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌───────────────┐   ┌────────────┐
  │ Collectors│→ │  Trend   │→ │   Style       │→ │  AI Content    │→ │  Quality    │
  │ (sources) │  │ Analyzer │  │ Intelligence  │  │  Generator     │  │  Gates      │
  └──────────┘   └──────────┘   └──────────────┘   └───────────────┘   └─────┬──────┘
       │              │               │                   │                  │
       ▼              ▼               ▼                   ▼                  ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │                        PostgreSQL (SQLAlchemy + Alembic)                         │
  │   articles · topics · trends · style_profiles · posts · approvals · analytics   │
  └────────────────────────────────────────────────────────────────────────────────┘
       ▲              ▲               ▲                   ▲                  │
       │           ChromaDB (embeddings: dedup + RAG)                       │
       │                                                                    ▼
  ┌────────────┐                                              ┌──────────────────────┐
  │  Analytics │◄─────────── feedback loop ──────────────────│  Approval System      │
  │  Collector │   (engagement → prompt tuning)              │  Dashboard + Email +  │
  └─────┬──────┘                                              │  Teams + Sheets       │
        │                                                     └──────────┬───────────┘
        │                                                                │ APPROVED
        ▼                                                                ▼
  LinkedIn API ◄──────────────────────────────────────────── LinkedIn Publisher
```

**Flow in one line:** collect → rank → learn style → generate → dedup+factcheck → approve → publish → measure → feed back.

---

## 2. Architecture Principles

| Principle | How applied |
|-----------|-------------|
| Clean / layered | `api → services → repositories → models`. No layer skips down more than one. |
| SOLID | Each collector/analyzer/publisher = one class, one job. Interfaces (ABCs) for swappable parts. |
| Dependency Injection | FastAPI `Depends()` wires repos+services. Constructors take interfaces, not concretes. |
| Repository pattern | DB access only through repos. Services never touch SQLAlchemy session directly. |
| Strategy pattern | `BaseCollector`, `BaseNotifier`, `BasePublisher` — add source/channel without touching pipeline. |
| Config as env | Pydantic `Settings`, `.env`. No hardcoded secrets. |
| Async where IO-bound | Collectors, HTTP, LinkedIn calls async. CPU work (embeddings) in threadpool. |

---

## 3. Module Build Order (incremental)

Build bottom-up so each layer testable before next.

```
Phase 0  Foundation     → config, logging, DB session, Docker, base ABCs
Phase 1  Persistence    → SQLAlchemy models + Alembic + repositories + seed
Phase 2  Collectors     → news sources, normalize, dedup, store
Phase 3  Trend Analyzer → scoring engine + topic ranking
Phase 4  Style Intel    → feature extraction from approved posts
Phase 5  AI Generator   → Ollama + prompt templates + RAG via ChromaDB
Phase 6  Quality Gates  → embedding dedup + fact verification
Phase 7  Approval       → dashboard, email, Teams, Sheets, JWT auth
Phase 8  Publisher      → LinkedIn API, retry, status tracking
Phase 9  Analytics      → engagement pull, weekly report, feedback loop
Phase 10 Scheduler+API  → APScheduler orchestration, full REST surface, tests
```

---

## 4. Module-by-Module Design

### Module 1 — Foundation (`utils/`, `database/`, root)
- `core/config.py` — Pydantic `Settings`, loads `.env` (DB URL, Ollama host, API keys, thresholds).
- `core/logging.py` — Python `logging` + `RotatingFileHandler` (10MB×5). JSON logs for prod.
- `database/session.py` — async SQLAlchemy engine, `get_db()` dependency.
- `core/base.py` — ABCs: `BaseCollector`, `BaseAnalyzer`, `BaseNotifier`, `BasePublisher`.
- Deliver: `Dockerfile`, `docker-compose.yml` (app + postgres + ollama + chromadb).

### Module 2 — Persistence (`models/`, `repositories/`)
- Normalized models (see §6).
- One repo per aggregate: `ArticleRepository`, `PostRepository`, `ApprovalRepository`, etc.
- Repo interface: `get/list/create/update/delete` + domain queries (`get_pending_approvals`).
- Alembic migrations. Seed script: 1 admin user, sample style profile, RSS source list.

### Module 3 — News Collectors (`collectors/`)
Each implements `BaseCollector.fetch() -> list[RawArticle]`.

| Collector | Source | Method | Auth |
|-----------|--------|--------|------|
| `RSSCollector` | TechCrunch, Google News RSS | `feedparser` | none |
| `HackerNewsCollector` | HN Firebase API | `requests` | none |
| `GitHubTrendingCollector` | GitHub API / trending | `requests` | token (rate limit) |
| `DevToCollector` | Dev.to API | `requests` | API key |
| `RedditCollector` | Reddit API (PRAW) | OAuth | client id/secret |

- `CollectorService` runs all concurrently (`asyncio.gather`), normalizes → `Article`, dedup by URL hash + title fuzzy match, stores.
- **Playwright only where ToS permits.** Never scrape LinkedIn member content.

### Module 4 — Trend Analyzer (`analyzers/trend_analyzer.py`)
- Input: recent articles. Output: ranked `Topic` + `Trend` rows with score.
- Score = weighted sum:
  ```
  trend_score = w1*popularity + w2*recency + w3*tech_relevance
              + w4*business_impact + w5*audience_relevance
  ```
  - popularity = source signals (HN points, GitHub stars, cross-source mention count).
  - recency = exponential decay on publish time.
  - relevance dims = Ollama classifier OR sentence-transformer cosine vs target-topic vectors.
- Cluster near-duplicate articles into one topic (embedding similarity).

### Module 5 — LinkedIn Content Intelligence (`analyzers/style_analyzer.py`)
- Input: **own approved past posts** + legally available reference text. Never copy.
- Extract features → `StyleProfile`:
  - hook style, CTA style, storytelling pattern (label via LLM)
  - emoji density, avg paragraph size, avg sentence length, hashtag count/style, formatting (bullets/line-breaks).
- Stored as structured JSON. Used as constraints in generation prompt.

### Module 6 — AI Content Generator (`ai/`)
- `ai/ollama_client.py` — async wrapper, model configurable (Llama 3.1 / Qwen / Mistral).
- `ai/prompts/` — versioned templates (see §8).
- RAG: pull top-K relevant articles from ChromaDB → ground the post (factuality).
- Generator produces structured JSON:
  ```json
  { "headline": "...", "hook": "...", "body": "...", "cta": "...",
    "hashtags": ["..."], "best_post_time": "...", "topic_reason": "..." }
  ```
- Inject `StyleProfile` + brand rules as system constraints.

### Module 7 — Quality Gates (`ai/dedup.py`, `ai/factcheck.py`)
- **Dedup:** embed draft (Sentence Transformers) → query ChromaDB vs past posts. If cosine > `SIMILARITY_THRESHOLD` (e.g. 0.85) → regenerate (max N retries).
- **Fact-check:** split draft into claims → for each, retrieve supporting article via embedding search → LLM verdict `supported/unsupported`. Unsupported → flag `needs_review`, surface in dashboard.

### Module 8 — Approval System (`api/approval`, `notifications/`)
- States: `DRAFT → PENDING → APPROVED | REJECTED | EDITED → REGENERATE`.
- Channels (all `BaseNotifier`):
  - `EmailNotifier` (Gmail API) — preview + approve/reject/regenerate links (signed tokens).
  - `TeamsNotifier` (webhook) — adaptive card.
  - `SheetsNotifier` — append draft row, watch status column.
- Dashboard (FastAPI + server-rendered or React) shows draft, trend score, hashtags, time, fact-check flags.
- **Hard rule:** publisher reads only `APPROVED` rows. No bypass path.

### Module 9 — LinkedIn Publisher (`publishers/linkedin_publisher.py`)
- Official LinkedIn Marketing/Posts API + OAuth2. UGC/Posts endpoint.
- On approve → publish → store `post_id`, `published_at`, `status`.
- Retry with exponential backoff (tenacity) on transient failure. Persist errors.
- Idempotency key to avoid double-post.

### Module 10 — Analytics (`analyzers/analytics_service.py`)
- Pull likes/comments/shares/impressions via LinkedIn API (where granted).
- Store time-series in `analytics`. Weekly report (top posts, engagement deltas).
- **Feedback loop:** aggregate high-performing patterns → bias future generation prompts (which hooks/topics/times worked).

### Module 11 — Scheduler & Orchestration (`scheduler/`)
- APScheduler job `daily_pipeline()` chains M3→M7, creates draft, fires notifications.
- Configurable cron via env. Manual trigger via `POST /admin/run-pipeline`.
- Each stage idempotent + logged; failure isolates stage, alerts admin.

---

## 5. Project Structure

```
linkedin_automation/
├── api/                 # FastAPI routers (auth, news, trends, generation, approval,
│   │                    #   publishing, analytics, admin, search, history)
│   └── deps.py          # DI: get_db, get_current_user, repo/service providers
├── core/                # config, logging, security(JWT), base ABCs, exceptions
├── models/              # SQLAlchemy ORM
├── schemas/             # Pydantic request/response DTOs
├── repositories/        # repository pattern (one per aggregate)
├── services/            # business logic, orchestration
├── collectors/          # RSS, HN, GitHub, Dev.to, Reddit
├── analyzers/           # trend, style, analytics
├── ai/                  # ollama client, prompts/, embeddings, dedup, factcheck
├── publishers/          # linkedin publisher
├── notifications/       # email(Gmail), teams, sheets
├── scheduler/           # APScheduler jobs
├── database/            # session, base, init
├── migrations/          # Alembic
├── utils/               # helpers, retry, rate-limit
├── tests/               # unit + integration (pytest)
├── seed/                # seed data
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 6. Database Models (normalized)

| Table | Key fields | Relations |
|-------|-----------|-----------|
| `users` | id, email, hashed_pw, role | → approvals |
| `articles` | id, source, url(uniq), title, content, published_at, url_hash | → topics(M2M) |
| `topics` | id, name, cluster_id | ← articles |
| `trends` | id, topic_id, score, popularity, recency, relevance, run_date | → topic |
| `style_profiles` | id, name, features(JSON), source | → posts |
| `generated_posts` | id, topic_id, style_id, headline, hook, body, cta, hashtags(JSON), best_time, reason, status | → approval, publishing, embedding |
| `approvals` | id, post_id, user_id, action, comment, decided_at | → post, user |
| `publishing_history` | id, post_id, linkedin_post_id, status, published_at, error, retries | → post |
| `analytics` | id, post_id, likes, comments, shares, impressions, captured_at | → post |
| `embeddings` | id, ref_type, ref_id, vector_id(Chroma) | polymorphic |
| `notifications` | id, post_id, channel, status, sent_at | → post |
| `account_posts` | id, linkedin_post_id, text, posted_at, media_type, length, hashtag_count, source(app/manual), eng_rate | → analytics |
| `engagement_insights` | id, metric, finding, confidence, generated_at | — |
| `improvement_tips` | id, account_post_id, category, suggestion, expected_lift | → account_posts |
| `audit_logs` | id, actor, action, entity, payload(JSON), ts | — |

ChromaDB holds the actual vectors; `embeddings` table maps SQL rows → Chroma IDs.

---

## 7. REST API Surface

```
POST   /auth/login                JWT issue
GET    /news                      list/filter articles
POST   /news/collect              manual collect trigger
GET    /trends                    ranked topics
POST   /trends/analyze            run analyzer
POST   /generate                  produce draft (topic_id)
GET    /approvals                 pending list
POST   /approvals/{id}/approve|reject|edit|regenerate
POST   /publish/{post_id}         publish approved (guarded)
GET    /analytics                 metrics + weekly report
GET    /search                    semantic search posts/articles
GET    /history                   post timeline
POST   /admin/run-pipeline        manual full run
GET    /admin/health|logs|scheduler
POST   /coach/sync                pull account posts + metrics
GET    /coach/audit               full account report
GET    /coach/app-impact          app-suggested vs manual lift %
GET    /coach/insights            mined engagement patterns
GET    /coach/tips                improvement suggestions
GET    /coach/post/{id}           per-post diagnosis + rewrite
```
All documented via Swagger/OpenAPI auto-gen. JWT + OAuth2 on protected routes.

---

## 8. Prompt Templates (`ai/prompts/`)

Versioned, single-responsibility, parameterized:

| File | Purpose |
|------|---------|
| `trend_analysis.txt` | score/classify article relevance dims |
| `style_analysis.txt` | extract writing features → JSON |
| `generation.txt` | create post from topic + style + RAG context |
| `factcheck.txt` | claim → supported/unsupported vs sources |
| `regeneration.txt` | rewrite given dedup/factcheck/edit feedback |
| `optimization.txt` | tune prompt using engagement winners |
| `coach_diagnosis.txt` | explain why a post under/over-performed + rewrite |

Keep prompts in files (not code) → editable without redeploy, version in git.

---

## 9. External Sources & Auth

| Service | Use | Credential |
|---------|-----|-----------|
| TechCrunch / Google News RSS | news | none |
| Hacker News API | news + popularity | none |
| GitHub API | trending repos | personal token |
| Dev.to API | articles | API key |
| Reddit API | discussions | OAuth client |
| Ollama (local) | LLM generation/analysis | host URL |
| LinkedIn API | publish + analytics | OAuth2 app |
| Gmail API | approval email | OAuth2 |
| Teams Webhook | notify | webhook URL |
| Google Sheets API | approval board | service account |

All keys via `.env` / Pydantic Settings. Rate-limit + retry wrappers per client.

---

## 10. Non-Functional

- Type hints everywhere; `mypy` clean.
- Async IO; CPU-bound embedding in threadpool executor.
- Rotating logs + structured fields + per-stage correlation id.
- Retry (tenacity) + circuit-break on external calls.
- Rate limiting per source (respect ToS).
- Docker + docker-compose (app, postgres, ollama, chromadb).
- Tests: unit (services, scoring, repos w/ mocks) + integration (pipeline, API). pytest + httpx + testcontainers.
- CI: lint + type + test gate.

---

## 11. Legal & Safety Guardrails

- **No LinkedIn scraping of member content.** Publish/read only via official API + user OAuth.
- Human approval mandatory — `publish` endpoint rejects non-`APPROVED` posts.
- Fact-check flags unsupported claims before human sees them.
- Audit log every state change.
- Originality enforced by embedding dedup; style learned, never copied.

---

## 12. Module — Profile & Engagement Coach

Self-audit your own LinkedIn account: detect which published posts came from this app, measure engagement, mine what drives it, output personalized improvement tips. Reads **only your own account via your OAuth** — no scraping.

**Provenance (app vs manual).** App already stores `linkedin_post_id` in `publishing_history` on publish. Match pulled account posts against it:
```
source = "app"     if linkedin_post_id ∈ publishing_history
source = "manual"  otherwise
```

**Engagement rate** (normalized by reach, comments/shares worth more):
```
eng_rate = (likes + 2·comments + 3·shares) / impressions
```

**App impact / lift:**
```
lift% = (avg_eng_app − avg_eng_manual) / avg_eng_manual · 100   # t-test for significance
```

**Pattern mining** — regression on YOUR posts (feeds §10 loop):
```
eng_rate ≈ w·[length, post_hour, day_of_week, hashtag_count,
              has_media, hook_type, emoji_count, has_question_cta]
```
Fitted weights reveal what matters for your audience (e.g. "8am +40%", "3 hashtags beat 10").

**Sub-features:** account audit · app-impact report · pattern insights · improvement tips · per-post diagnosis+rewrite (LLM) · trend-correlation (Pearson trend_score vs engagement).

**Math:** weighted engagement score · linear/logistic regression · per-hour histogram (best time) · length curve fit · t-test (app vs manual) · Pearson correlation (topic effect).

**Feedback:** mined weights bias §6 generation prompt → app learns your audience, closing generate→publish→measure→learn loop. Tables: `account_posts`, `engagement_insights`, `improvement_tips`. API under `/coach/*`. Prompt `coach_diagnosis.txt`.

---

## 13. Suggested Build Sequence (dev tasks)

1. Scaffold repo + Docker + config + logging.
2. Models + Alembic + repos + seed.
3. One collector (RSS) end-to-end + tests → add rest.
4. Trend scoring + topic clustering.
5. Style extractor on seed posts.
6. Ollama client + generation prompt + RAG.
7. Dedup + factcheck gates.
8. Approval dashboard + email/Teams/Sheets + JWT.
9. LinkedIn publisher + retry.
10. Analytics + weekly report + feedback into prompts.
11. Profile & Engagement Coach (account sync, provenance tag, pattern mining, tips).
12. Wire APScheduler + finalize REST + integration tests + README.
```
```
