"""Application settings.

All configuration is read from environment variables (loaded from a local
`.env` file in development). Nothing secret is ever hard-coded. Import
`get_settings()` everywhere instead of touching the environment directly so the
config is parsed and validated in exactly one place.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated view of the process environment.

    Values come from (in priority order) real environment variables, then the
    `.env` file. Unknown keys in `.env` are ignored so the file can hold notes
    or future settings without breaking startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------
    app_name: str = Field(default="LinkedIn Thought-Leadership Agent")
    environment: str = Field(default="development")  # development | production | test
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # --- Security ------------------------------------------------------------
    # Used to sign JWTs (Phase 7). Override with a strong random value in prod.
    secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=60 * 12)
    # Public base URL used to build one-click approve/reject links in notifications.
    public_base_url: str = Field(default="http://localhost:8000")
    # TTL for the signed action token embedded in those one-click links.
    action_token_expire_minutes: int = Field(default=60 * 24 * 3)

    # --- Database ------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/linkedin_agent"
    )
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)

    # --- External services ---------------------------------------------------
    ollama_host: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1")
    ollama_timeout_seconds: float = Field(default=600.0)  # CPU cold-load can be slow
    ollama_temperature: float = Field(default=0.7)
    ollama_num_predict: int = Field(default=700)  # cap output tokens to bound latency
    chroma_host: str = Field(default="http://localhost:8001")
    # Local embedded Chroma store (no separate server needed in dev).
    chroma_path: str = Field(default=".chroma")
    chroma_collection: str = Field(default="articles")
    # Past published/accepted posts live in their own collection for dedup (Phase 6).
    chroma_posts_collection: str = Field(default="posts")

    # --- Generator (Phase 5) -------------------------------------------------
    rag_top_k: int = Field(default=5)  # grounding articles pulled per topic
    # Non-negotiable rules injected into every generation prompt.
    brand_rules: str = Field(
        default=(
            "Write original analysis, never copy article sentences. "
            "Be factual and grounded only in the provided facts — invent nothing. "
            "Professional, insightful, concise thought-leadership voice. "
            "No hype, no clickbait, no false claims, no hashtags stuffing."
        )
    )

    # --- Quality gates (Phase 6) ---------------------------------------------
    quality_gates_enabled: bool = Field(default=True)  # run dedup + fact-check after generate
    # Gate 1 — duplicate detection. Cosine similarity (0–1) to the nearest past
    # post above this is "too similar"; regenerate up to N times before flagging.
    dedup_similarity_threshold: float = Field(default=0.85)
    dedup_max_regen_tries: int = Field(default=2)
    # Gate 2 — fact check. Cap claims verified per post (bounds LLM latency on CPU);
    # claims shorter than this are treated as fluff and skipped.
    factcheck_max_claims: int = Field(default=6)
    factcheck_min_claim_chars: int = Field(default=40)
    factcheck_rag_k: int = Field(default=3)  # candidate sources fetched per claim

    # --- Notifications (Phase 7) ---------------------------------------------
    # Comma-separated channels to fan a PENDING draft out to. Unknown/unconfigured
    # channels fall back to the log notifier so the app always works offline.
    notification_channels: str = Field(default="log")  # log,email,teams,sheets
    notify_to_email: str = Field(default="")  # approver inbox for email channel
    gmail_credentials_file: str = Field(default="")  # OAuth client secrets json
    gmail_token_file: str = Field(default=".secrets/gmail_token.json")
    teams_webhook_url: str = Field(default="")  # incoming-webhook connector URL
    sheets_credentials_file: str = Field(default="")  # service-account json
    sheets_spreadsheet_id: str = Field(default="")
    sheets_worksheet: str = Field(default="Approvals")

    # --- LinkedIn publisher (Phase 8) ----------------------------------------
    # Official API only — no scraping. One-time OAuth2 gives a member access token
    # and the author URN; both live in `.env`, never in code.
    linkedin_access_token: str = Field(default="")  # member OAuth2 access token
    linkedin_author_urn: str = Field(default="")  # e.g. urn:li:person:xxxx
    linkedin_api_base: str = Field(default="https://api.linkedin.com")
    linkedin_timeout_seconds: float = Field(default=20.0)
    # Retry budget for a transient publish failure (5xx/timeout/429). 4xx auth
    # errors are never retried — they fail fast so a bad token surfaces at once.
    publish_max_tries: int = Field(default=5)

    # --- Collector sources (Phase 2) -----------------------------------------
    github_token: str = Field(default="")
    devto_api_key: str = Field(default="")
    reddit_client_id: str = Field(default="")
    reddit_client_secret: str = Field(default="")
    reddit_user_agent: str = Field(default="linkedin-agent/0.1 by u/unknown")
    reddit_subreddits: str = Field(default="programming,technology,MachineLearning")

    # Collector tuning
    collector_timeout_seconds: float = Field(default=15.0)
    collector_max_concurrency: int = Field(default=5)
    collector_per_source_limit: int = Field(default=25)
    dedup_title_threshold: int = Field(default=90)  # rapidfuzz % similarity

    # Retention / lifecycle (raw articles are an ephemeral working set)
    article_ttl_days: int = Field(default=21)  # delete article rows older than this
    content_ttl_days: int = Field(default=3)  # null heavy `content` text after this
    seen_hash_ttl_days: int = Field(default=60)  # dedup memory horizon

    # --- Trend analyzer (Phase 3) --------------------------------------------
    embedding_model: str = Field(default="all-MiniLM-L6-v2")  # sentence-transformers
    # DBSCAN: cosine distance. eps = max distance to be "same story"; min_samples=1
    # so a unique article is still its own topic (no points dropped as noise).
    cluster_eps: float = Field(default=0.45)
    cluster_min_samples: int = Field(default=1)
    # How far back to pull articles for an analysis run, and a hard cap per run.
    analyze_window_hours: int = Field(default=72)
    analyze_max_articles: int = Field(default=500)
    # Recency decay: score halves every `recency_half_life_hours`.
    recency_half_life_hours: float = Field(default=24.0)
    # Trend score weights (popularity + recency + relevance). Tuned later (Phase 9/10).
    weight_popularity: float = Field(default=0.4)
    weight_recency: float = Field(default=0.3)
    weight_relevance: float = Field(default=0.3)
    # Reference themes the topic vector is scored against for relevance (0–1 cosine).
    trend_themes: str = Field(
        default="artificial intelligence and machine learning"
        ";software engineering and developer tools"
        ";startups, technology business and product strategy"
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    `lru_cache` makes this a process-wide singleton: the environment is parsed
    once. Call `get_settings.cache_clear()` in tests to force a reload.
    """

    return Settings()
