"""Daily pipeline orchestration (Phase 11).

Chains the steps the scheduler runs once a day, the same ones exposed
individually as REST endpoints:

    collect news → analyze trends → generate top-N drafts → submit (notify)
    → (optional) prune

Each draft is `submit`ted, which moves it to PENDING and fans a notification
(WhatsApp + any other configured channel) out with one-click approve links.
Per-topic generation failures are isolated so one bad topic never aborts the
whole run. Everything is built from a single DB session passed in by the caller
(the scheduler opens one per run).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

from app.ai.dedup import PostDedup
from app.ai.factcheck import FactChecker
from app.analyzers.trend_analyzer import TrendAnalyzer
from app.core.config import Settings, get_settings
from app.notifications.service import NotificationService
from app.repositories.repos import (
    ApprovalRepository,
    ArticleRepository,
    AuditLogRepository,
    NotificationRepository,
    PostRepository,
    SeenHashRepository,
    StyleProfileRepository,
    TopicRepository,
    TrendRepository,
)
from app.services.approval_service import ApprovalService
from app.services.collector_service import CollectorService, build_default_collectors
from app.services.generator_service import GeneratorService, TopicNotFound
from app.services.retention_service import RetentionService

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    collected: dict = field(default_factory=dict)
    analyzed: dict = field(default_factory=dict)
    generated_post_ids: list[int] = field(default_factory=list)
    submitted: int = 0
    errors: list[str] = field(default_factory=list)
    pruned: dict | None = None

    def as_dict(self) -> dict:
        return {
            "collected": self.collected,
            "analyzed": self.analyzed,
            "generated_post_ids": self.generated_post_ids,
            "submitted": self.submitted,
            "errors": self.errors,
            "pruned": self.pruned,
        }


class PipelineService:
    """Runs the full daily chain on one DB session."""

    def __init__(self, db: Session, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def run_daily(self, *, top_n: int | None = None, style_name: str = "default") -> PipelineResult:
        top_n = top_n if top_n is not None else self.settings.daily_top_n
        result = PipelineResult()

        articles = ArticleRepository(self.db)
        seen = SeenHashRepository(self.db)
        topics = TopicRepository(self.db)
        trends = TrendRepository(self.db)

        # 1. Collect news -----------------------------------------------------
        try:
            timeout = httpx.Timeout(self.settings.collector_timeout_seconds)
            async with httpx.AsyncClient(
                timeout=timeout, headers={"User-Agent": "linkedin-agent/0.1"}
            ) as client:
                collectors = build_default_collectors(client, self.settings)
                collector = CollectorService(
                    articles,
                    collectors,
                    seen_repo=seen,
                    max_concurrency=self.settings.collector_max_concurrency,
                    title_threshold=self.settings.dedup_title_threshold,
                )
                result.collected = (await collector.collect()).as_dict()
        except Exception as exc:  # collection is best-effort; analysis can still run
            logger.warning("Pipeline: collection failed", exc_info=True)
            result.errors.append(f"collect: {exc}")

        # 2. Analyze trends ---------------------------------------------------
        try:
            analyzer = TrendAnalyzer(articles, topics, trends, settings=self.settings)
            result.analyzed = (await analyzer.run()).as_dict()
        except Exception as exc:
            logger.warning("Pipeline: trend analysis failed", exc_info=True)
            result.errors.append(f"analyze: {exc}")

        # 3. Generate top-N drafts -------------------------------------------
        ranked = trends.ranked(limit=top_n)
        if not ranked:
            result.errors.append("no ranked topics to generate from")
        for trend in ranked:
            try:
                post = await self._generate_one(trend.topic_id, style_name)
                result.generated_post_ids.append(post.id)
                # 4. Submit → PENDING + notify (WhatsApp etc.)
                self._submit(post.id)
                result.submitted += 1
            except TopicNotFound as exc:
                result.errors.append(f"topic {trend.topic_id}: {exc}")
            except Exception as exc:
                logger.warning("Pipeline: generate/submit failed for topic %s", trend.topic_id, exc_info=True)
                result.errors.append(f"topic {trend.topic_id}: {exc}")

        # 5. Prune (retention) ------------------------------------------------
        if self.settings.daily_pipeline_prune:
            try:
                result.pruned = RetentionService(articles, seen).run().as_dict()
            except Exception as exc:
                logger.warning("Pipeline: prune failed", exc_info=True)
                result.errors.append(f"prune: {exc}")

        logger.info(
            "Daily pipeline done: %d generated, %d submitted, %d errors",
            len(result.generated_post_ids), result.submitted, len(result.errors),
        )
        return result

    # --- internals -----------------------------------------------------------

    async def _generate_one(self, topic_id: int, style_name: str):
        topics = TopicRepository(self.db)
        articles = ArticleRepository(self.db)
        styles = StyleProfileRepository(self.db)
        posts = PostRepository(self.db)
        dedup = factcheck = None
        if self.settings.quality_gates_enabled:
            dedup = PostDedup(settings=self.settings)
            factcheck = FactChecker(settings=self.settings)
        generator = GeneratorService(
            topics, articles, styles, posts, dedup=dedup, factcheck=factcheck, settings=self.settings
        )
        return await generator.generate(topic_id, style_name=style_name)

    def _submit(self, post_id: int) -> None:
        posts = PostRepository(self.db)
        approvals = ApprovalRepository(self.db)
        audit = AuditLogRepository(self.db)
        notifier = NotificationService(NotificationRepository(self.db), settings=self.settings)
        service = ApprovalService(posts, approvals, audit, notifier=notifier)
        service.submit(post_id)
