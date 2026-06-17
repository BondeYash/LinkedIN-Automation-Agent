"""Unit tests for the trend scoring math (pure functions, fixed numbers)."""

from __future__ import annotations

import math

from app.analyzers import scoring


def test_engagement_sums_known_signals_and_ignores_junk():
    raw = {"score": 120, "stars": 30, "comments": 10, "language": "Python", "flag": True}
    # 120 + 30 + 10 = 160; "language" (str) and True (bool) ignored.
    assert scoring.engagement_of(raw) == 160.0
    assert scoring.engagement_of({}) == 0.0
    assert scoring.engagement_of(None) == 0.0


def test_raw_popularity_is_log_compressed():
    # log1p(engagement + source_count)
    assert scoring.raw_popularity(0, 0) == 0.0
    assert scoring.raw_popularity(99, 1) == math.log1p(100)
    # viral item doesn't blow up linearly
    assert scoring.raw_popularity(10_000, 1) < 2 * scoring.raw_popularity(100, 1)


def test_recency_decays_and_older_scores_lower():
    half_life = 24.0
    assert scoring.recency(0, half_life) == 1.0
    assert math.isclose(scoring.recency(24, half_life), 0.5, rel_tol=1e-9)
    assert math.isclose(scoring.recency(48, half_life), 0.25, rel_tol=1e-9)
    assert scoring.recency(72, half_life) < scoring.recency(24, half_life)
    assert scoring.recency(10, 0) == 0.0  # guard: non-positive half-life


def test_normalize_min_max_to_unit_range():
    assert scoring.normalize([1.0, 3.0, 5.0]) == [0.0, 0.5, 1.0]
    # all equal -> all share top rank, none penalized
    assert scoring.normalize([2.0, 2.0]) == [1.0, 1.0]
    assert scoring.normalize([]) == []
    assert scoring.normalize([7.0]) == [1.0]


def test_clamp01_bounds():
    assert scoring.clamp01(-0.5) == 0.0
    assert scoring.clamp01(0.3) == 0.3
    assert scoring.clamp01(1.7) == 1.0


def test_combine_weighted_sum():
    weights = scoring.ScoreWeights(popularity=0.5, recency=0.3, relevance=0.2)
    # 0.5*1 + 0.3*1 + 0.2*1 = 1.0
    assert math.isclose(scoring.combine(1.0, 1.0, 1.0, weights), 1.0, rel_tol=1e-9)
    # 0.5*0.4 + 0.3*0.0 + 0.2*1.0 = 0.4
    assert math.isclose(scoring.combine(0.4, 0.0, 1.0, weights), 0.4, rel_tol=1e-9)
    # out-of-range inputs are clamped before weighting
    assert math.isclose(scoring.combine(2.0, -1.0, 0.5, weights), 0.6, rel_tol=1e-9)
