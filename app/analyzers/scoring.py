"""Trend scoring math — pure functions, no DB, no model.

Kept separate from the analyzer so the formulas can be unit-tested with fixed
numbers. Every component is normalized to 0–1 before being combined, so the
weights are comparable and the final score is bounded.

    trend_score = w_pop·popularity + w_rec·recency + w_rel·relevance
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Keys in an article's `raw_signals` that count as engagement/popularity.
ENGAGEMENT_KEYS = ("score", "stars", "points", "comments", "reactions", "descendants")


@dataclass(frozen=True)
class ScoreWeights:
    popularity: float = 0.4
    recency: float = 0.3
    relevance: float = 0.3


def engagement_of(raw_signals: dict | None) -> float:
    """Sum the numeric engagement signals on one article (ignores non-numbers)."""
    if not raw_signals:
        return 0.0
    total = 0.0
    for key in ENGAGEMENT_KEYS:
        value = raw_signals.get(key)
        if isinstance(value, bool):  # bool is an int subclass — exclude it
            continue
        if isinstance(value, (int, float)):
            total += float(value)
    return total


def raw_popularity(total_engagement: float, source_count: int) -> float:
    """Compress raw engagement with log so one viral item can't dominate.

    `source_count` (how many sources carried the story) is folded in: broad
    coverage is itself a popularity signal. Result is unbounded — normalize it
    across the run with `normalize` before weighting.
    """
    return math.log1p(max(0.0, total_engagement) + max(0, source_count))


def recency(hours_old: float, half_life_hours: float) -> float:
    """Exponential decay in [0, 1]: 1.0 now, 0.5 at one half-life, →0 when old."""
    if half_life_hours <= 0:
        return 0.0
    hours_old = max(0.0, hours_old)
    lam = math.log(2) / half_life_hours
    return math.exp(-lam * hours_old)


def clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def normalize(values: list[float]) -> list[float]:
    """Min-max scale a list to 0–1. All-equal (or single) → all 1.0 (they share
    the rank, none is penalized)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0 for _ in values]
    span = hi - lo
    return [(v - lo) / span for v in values]


def combine(
    popularity: float, recency_: float, relevance: float, weights: ScoreWeights
) -> float:
    """Weighted sum of the three normalized signals → final trend score (0–1)."""
    return (
        weights.popularity * clamp01(popularity)
        + weights.recency * clamp01(recency_)
        + weights.relevance * clamp01(relevance)
    )
