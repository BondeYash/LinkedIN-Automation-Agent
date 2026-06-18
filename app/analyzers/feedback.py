"""Feedback loop — let what performed shape what gets written next.

Reads the top-engagement posts, extracts the patterns they share (hook style,
body length band, hashtag count, best post hour) and writes them as plain-English
tuning hints into `ai/prompts/optimization.txt`. The generator injects that file
into every prompt (see `generator_service`), so future drafts lean toward what
actually worked — closing the collect → publish → measure → improve loop.

Guardrails:
- Below `feedback_min_posts` measured posts the sample is too small to trust, so
  the file is left untouched (no chasing noise).
- The file is fully rewritten each run with a header marking it machine-managed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import Settings, get_settings
from app.repositories.repos import PostRepository

logger = logging.getLogger(__name__)

_OPT_PATH = Path(__file__).resolve().parent.parent / "ai" / "prompts" / "optimization.txt"

_HEADER = (
    "OPTIMIZATION HINTS (auto-tuned from your best-performing posts — "
    "treat as guidance, not hard rules)\n"
)


class FeedbackTuner:
    def __init__(
        self,
        posts: PostRepository,
        *,
        settings: Settings | None = None,
        path: Path | None = None,
    ) -> None:
        self.posts = posts
        self.settings = settings or get_settings()
        self.path = path or _OPT_PATH

    def run(self, report: dict) -> str | None:
        """Derive hints from `report` (a WeeklyReport.build() dict) and write
        them. Returns the hint text written, or None if the sample was too small."""
        top = report.get("top_posts") or []
        if len(top) < self.settings.feedback_min_posts:
            logger.info(
                "Feedback skipped: only %d measured posts (< %d).",
                len(top), self.settings.feedback_min_posts,
            )
            return None

        hints = self._derive(report, top)
        text = _HEADER + "\n".join(f"- {h}" for h in hints) + "\n"
        self.path.write_text(text, encoding="utf-8")
        logger.info("Wrote %d optimization hints to %s", len(hints), self.path)
        return text

    # --- derivation ----------------------------------------------------------

    def _derive(self, report: dict, top: list[dict]) -> list[str]:
        hints: list[str] = []

        # Body length band of winning posts.
        lengths = [len(p.body) for p in self._top_models(top) if p and p.body]
        if lengths:
            avg = sum(lengths) // len(lengths)
            band = _length_band(avg)
            hints.append(
                f"Aim for {band} posts (~{avg} characters) — that length earned the most engagement."
            )

        # Hashtag count.
        tag_counts = [len(p.hashtags or []) for p in self._top_models(top) if p]
        if tag_counts:
            avg_tags = round(sum(tag_counts) / len(tag_counts))
            hints.append(f"Use about {avg_tags} hashtags — top posts averaged that many.")

        # Hook style.
        hook_style = self._dominant_hook_style(top)
        if hook_style:
            hints.append(hook_style)

        # Best topics.
        topics = [t.get("topic") for t in (report.get("best_topics") or [])[:3] if t.get("topic")]
        if topics:
            hints.append("Topics that resonated most: " + ", ".join(topics) + ".")

        # Best hours.
        hours = [h.get("hour") for h in (report.get("best_hours") or [])[:2] if h.get("hour") is not None]
        if hours:
            pretty = ", ".join(f"{int(h):02d}:00" for h in hours)
            hints.append(f"Engagement peaked for posts published around {pretty}.")

        # Best hashtags.
        tags = [t.get("hashtag") for t in (report.get("best_hashtags") or [])[:5] if t.get("hashtag")]
        if tags:
            hints.append("High-performing hashtags to consider: " + ", ".join(f"#{t}" for t in tags) + ".")

        return hints or ["No strong pattern yet — keep writing original, grounded posts."]

    def _top_models(self, top: list[dict]):
        return [self.posts.get(int(p["post_id"])) for p in top]

    def _dominant_hook_style(self, top: list[dict]) -> str | None:
        styles: dict[str, int] = {}
        for post in self._top_models(top):
            if not post:
                continue
            text = (post.hook or post.headline or "").strip()
            style = _classify_hook(text)
            if style:
                styles[style] = styles.get(style, 0) + 1
        if not styles:
            return None
        winner = max(styles, key=styles.get)
        templates = {
            "question": "Open with a question — your best posts hooked readers that way.",
            "number": "Lead with a number or stat — that hook drove the most engagement.",
            "bold": "Open with a bold, contrarian claim — it outperformed softer openers.",
        }
        return templates.get(winner)


# --- heuristics --------------------------------------------------------------


def _length_band(chars: int) -> str:
    if chars < 600:
        return "short"
    if chars < 1300:
        return "medium-length"
    return "long-form"


def _classify_hook(text: str) -> str | None:
    if not text:
        return None
    if "?" in text:
        return "question"
    if any(c.isdigit() for c in text[:40]):
        return "number"
    return "bold"
