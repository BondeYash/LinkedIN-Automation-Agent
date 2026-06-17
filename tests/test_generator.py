"""Generator tests — JSON parsing and the full generate flow with fakes."""

from __future__ import annotations

import pytest

from app.ai.rag import GroundingFact
from app.models.enums import PostStatus
from app.models.models import GeneratedPost, StyleProfile, Topic, Trend
from app.services.generator_service import (
    GeneratorService,
    TopicNotFound,
    parse_post_json,
)

_GOOD_JSON = """{
  "headline": "AI is eating the org chart",
  "hook": "Everyone talks about AI tools. Few talk about AI teams.",
  "body": "Here is the shift.\\nSmall teams now ship like big ones.",
  "cta": "How is your team adapting?",
  "hashtags": ["#AI", "#Leadership", "future-of-work"],
  "best_post_time": "Tuesday 9:00 AM",
  "topic_reason": "It is peaking on the trend index this week."
}"""


def test_parse_strips_code_fences_and_prose():
    fenced = "Sure, here you go:\n```json\n" + _GOOD_JSON + "\n```"
    data = parse_post_json(fenced)
    assert data["headline"].startswith("AI is eating")
    assert data["hashtags"][0] == "#AI"


def test_parse_rejects_missing_keys():
    with pytest.raises(ValueError):
        parse_post_json('{"headline": "x"}')


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        parse_post_json("no json here at all")


# --- fakes ------------------------------------------------------------------


class _FakeDB:
    def commit(self):
        pass


class _FakeTopicRepo:
    def __init__(self, topic):
        self._topic = topic

    def get(self, topic_id):
        return self._topic if (self._topic and self._topic.id == topic_id) else None


class _FakeStyleRepo:
    def __init__(self, profile):
        self._profile = profile

    def get_by_name(self, name):
        return self._profile


class _FakePostRepo:
    def __init__(self):
        self.saved = []
        self.db = _FakeDB()

    def create(self, obj, *, commit=False):
        obj.id = len(self.saved) + 1
        self.saved.append(obj)
        return obj


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.prompt = None

    async def generate(self, prompt, *, json_mode=False):
        self.prompt = prompt
        return self.response


class _FakeRAG:
    def __init__(self, facts):
        self._facts = facts

    def query(self, text, *, k=5):
        return self._facts


def _topic():
    t = Topic(name="AI-native startups")
    t.id = 7
    t.trends = [Trend(topic_id=7, score=0.82)]
    t.articles = []
    return t


async def test_generate_saves_draft_with_parsed_fields():
    topic = _topic()
    style = StyleProfile(name="default", features={"avg_word_count": 40})
    style.id = 1
    posts = _FakePostRepo()
    llm = _FakeLLM(_GOOD_JSON)
    facts = [GroundingFact(title="Funding round", source="techcrunch", url="https://x/1")]

    service = GeneratorService(
        _FakeTopicRepo(topic),
        article_repo=None,
        style_repo=_FakeStyleRepo(style),
        post_repo=posts,
        llm=llm,
        rag=_FakeRAG(facts),
    )

    post: GeneratedPost = await service.generate(7, style_name="default")

    assert post.status == PostStatus.DRAFT
    assert post.topic_id == 7 and post.style_id == 1
    assert post.trend_score == 0.82
    assert post.body.startswith("Here is the shift")
    # hashtags cleaned: leading '#' stripped
    assert post.hashtags == ["AI", "Leadership", "future-of-work"]
    assert len(posts.saved) == 1
    # grounding fact made it into the prompt
    assert "Funding round" in llm.prompt
    # brand rules injected
    assert "never copy" in llm.prompt.lower()


async def test_generate_unknown_topic_raises():
    service = GeneratorService(
        _FakeTopicRepo(None),
        article_repo=None,
        style_repo=_FakeStyleRepo(None),
        post_repo=_FakePostRepo(),
        llm=_FakeLLM(_GOOD_JSON),
        rag=_FakeRAG([]),
    )
    with pytest.raises(TopicNotFound):
        await service.generate(999)


async def test_generate_propagates_bad_llm_output():
    topic = _topic()
    service = GeneratorService(
        _FakeTopicRepo(topic),
        article_repo=None,
        style_repo=_FakeStyleRepo(None),
        post_repo=_FakePostRepo(),
        llm=_FakeLLM("garbage, no json"),
        rag=_FakeRAG([]),
    )
    with pytest.raises(ValueError):
        await service.generate(7)
