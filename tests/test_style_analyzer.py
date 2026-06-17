"""Tests for style feature extraction and the style analyzer."""

from __future__ import annotations

from app.analyzers import style_features
from app.analyzers.style_analyzer import StyleAnalyzer
from app.models.models import StyleProfile


def test_post_features_basic_counts():
    text = "Big news today! We shipped it. 🚀\n\nProud of the team.\n\n#launch #startups"
    f = style_features.post_features(text)

    assert f["hashtag_count"] == 2
    assert f["emoji_count"] == 1
    assert f["paragraph_count"] == 3
    assert f["sentence_count"] >= 2
    assert f["hashtags_trailing"] is True  # hashtags sit in the final paragraph
    assert f["word_count"] > 0


def test_question_and_allcaps_hooks_detected():
    q = style_features.post_features("Are you measuring the right metric?\n\nHere's why.")
    assert q["hook_is_question"] is True

    caps = style_features.post_features("STOP optimizing the wrong thing.\n\nDo this instead.")
    assert caps["hook_has_allcaps"] is True


def test_aggregate_returns_ratios_and_no_raw_text():
    posts = [
        "Short one. #a",
        "Are you ready?\n\n- one\n- two\n\n#b #c",
    ]
    agg = style_features.aggregate(posts)

    assert agg["sample_size"] == 2
    assert 0.0 <= agg["bullet_usage_ratio"] <= 1.0
    assert agg["avg_hashtag_count"] == 1.5  # (1 + 2) / 2
    # crucial: the profile holds only numbers, never copied sentences
    blob = " ".join(str(v) for v in agg.values())
    assert "Are you ready" not in blob and "Short one" not in blob


def test_aggregate_empty_is_safe():
    assert style_features.aggregate([])["sample_size"] == 0
    assert style_features.aggregate(["   ", ""])["sample_size"] == 0


class _FakeStyleRepo:
    def __init__(self):
        self.saved: dict[str, StyleProfile] = {}
        self.db = type("DB", (), {"commit": lambda self: None})()

    def get_by_name(self, name):
        return self.saved.get(name)

    def create(self, obj, *, commit=False):
        obj.id = len(self.saved) + 1
        self.saved[obj.name] = obj
        return obj

    def update(self, obj, *, commit=False):
        self.saved[obj.name] = obj
        return obj


async def test_analyzer_saves_profile_and_upserts():
    repo = _FakeStyleRepo()
    analyzer = StyleAnalyzer(repo)  # NullStyleLabeler -> no labels

    p1 = await analyzer.build(["Hello world. #x"], name="default", source="seed")
    assert p1.name == "default"
    assert p1.features["sample_size"] == 1
    assert "labels" not in p1.features  # stub labeler adds nothing

    # second build with same name updates in place, not a duplicate
    p2 = await analyzer.build(["A. B. C. #y #z", "Another one here."], name="default")
    assert len(repo.saved) == 1
    assert p2.features["sample_size"] == 2


async def test_analyzer_rejects_empty_input():
    repo = _FakeStyleRepo()
    analyzer = StyleAnalyzer(repo)
    try:
        await analyzer.build(["  ", ""], name="default")
        assert False, "expected ValueError"
    except ValueError:
        pass
