"""Phase 6 quality-gate tests — dedup math, claim splitting, fact-check parsing,
and the generator's gate wiring (regeneration + NEEDS_REVIEW), all with fakes."""

from __future__ import annotations

import numpy as np

from app.ai.dedup import DedupVerdict, PostDedup
from app.ai.factcheck import ClaimCheck, FactChecker, FactVerdict, split_claims
from app.ai.rag import GroundingFact
from app.core.config import Settings
from app.models.enums import PostStatus
from app.models.models import GeneratedPost, StyleProfile, Topic, Trend
from app.services.generator_service import GeneratorService

_GOOD_JSON = """{
  "headline": "AI is eating the org chart",
  "hook": "Everyone talks about AI tools.",
  "body": "Small teams now ship like big ones. Funding into AI agents tripled last quarter according to the report.",
  "cta": "How is your team adapting?",
  "hashtags": ["#AI"],
  "topic_reason": "It is peaking this week."
}"""


# --- Gate 1: dedup ----------------------------------------------------------


class _FakeEmbedder:
    def embed(self, texts):
        return np.ones((len(texts), 3), dtype=np.float32)


class _FakeColl:
    def __init__(self, *, count, distance=None, ids=None):
        self._count = count
        self._distance = distance
        self._ids = ids or ["1"]
        self.upserts = []

    def count(self):
        return self._count

    def query(self, *, query_embeddings, n_results):
        return {"distances": [[self._distance]], "ids": [self._ids]}

    def upsert(self, **kw):
        self.upserts.append(kw)


def _dedup(coll):
    d = PostDedup(embedder=_FakeEmbedder(), settings=Settings())
    d._collection = coll
    return d


def test_dedup_empty_store_never_duplicate():
    v = _dedup(_FakeColl(count=0)).check("anything")
    assert v == DedupVerdict(is_duplicate=False, score=0.0, matched_post_id=None)


def test_dedup_flags_high_similarity():
    # distance 0.05 -> cosine similarity 0.95, above 0.85 threshold
    v = _dedup(_FakeColl(count=3, distance=0.05, ids=["7"])).check("dup text")
    assert v.is_duplicate is True
    assert v.score == 0.95 and v.matched_post_id == "7"


def test_dedup_passes_low_similarity():
    v = _dedup(_FakeColl(count=3, distance=0.6)).check("fresh text")
    assert v.is_duplicate is False and v.score == 0.4


def test_dedup_add_upserts_one_vector():
    coll = _FakeColl(count=0)
    _dedup(coll).add("42", "some post text")
    assert len(coll.upserts) == 1 and coll.upserts[0]["ids"] == ["42"]


# --- Gate 2: fact check -----------------------------------------------------


def test_split_claims_drops_short_fluff_and_caps():
    body = "Hi.\nThis is a long enough factual claim about the market growing fast.\nGo!"
    claims = split_claims(body, min_chars=20, max_claims=5)
    assert claims == ["This is a long enough factual claim about the market growing fast."]


class _FakeRAG:
    def __init__(self, facts):
        self._facts = facts

    def query(self, text, *, k=5):
        return self._facts


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.prompt = None

    async def generate(self, prompt, *, json_mode=False):
        self.prompt = prompt
        return self.response


def _settings():
    return Settings(factcheck_min_claim_chars=20, factcheck_max_claims=5)


async def test_factcheck_flags_unsupported_claim():
    facts = [GroundingFact(title="Report", source="techcrunch", url="https://x/1")]
    llm = _FakeLLM('{"claims": [{"index": 0, "supported": false, "reason": "no"}]}')
    fc = FactChecker(rag=_FakeRAG(facts), llm=llm, settings=_settings())
    verdict = await fc.check("This long claim asserts the market doubled overnight, supposedly.")
    assert not verdict.all_supported
    assert len(verdict.unsupported) == 1
    assert verdict.unsupported[0].source == "techcrunch"


async def test_factcheck_passes_supported_claim():
    llm = _FakeLLM('{"claims": [{"index": 0, "supported": true}]}')
    fc = FactChecker(rag=_FakeRAG([]), llm=llm, settings=_settings())
    verdict = await fc.check("This is a sufficiently long and grounded factual statement here.")
    assert verdict.all_supported


async def test_factcheck_empty_body_short_circuits():
    fc = FactChecker(rag=_FakeRAG([]), llm=_FakeLLM("{}"), settings=_settings())
    verdict = await fc.check("Hi.")  # too short to be a claim
    assert verdict.all_supported and verdict.checks == []


def test_factcheck_parse_fails_closed_on_garbage():
    assert FactChecker._parse("not json", 2) == {}


# --- Generator wiring -------------------------------------------------------


class _FakeDB:
    def commit(self):
        pass


class _FakeTopicRepo:
    def __init__(self, topic):
        self._topic = topic

    def get(self, topic_id):
        return self._topic if (self._topic and self._topic.id == topic_id) else None


class _FakeStyleRepo:
    def get_by_name(self, name):
        return StyleProfile(name=name, features={})


class _FakePostRepo:
    def __init__(self):
        self.saved = []
        self.db = _FakeDB()

    def create(self, obj, *, commit=False):
        obj.id = len(self.saved) + 1
        self.saved.append(obj)
        return obj


class _FakeRAGGround:
    def query(self, text, *, k=5):
        return []


class _FakeDedup:
    def __init__(self, *, duplicate):
        self._duplicate = duplicate
        self.added = []

    def check(self, text):
        return DedupVerdict(is_duplicate=self._duplicate, score=0.91, matched_post_id="3")

    def add(self, post_id, text):
        self.added.append(post_id)


class _FakeFactCheck:
    def __init__(self, verdict):
        self._verdict = verdict

    async def check(self, body):
        return self._verdict


def _topic():
    t = Topic(name="AI-native startups")
    t.id = 7
    t.trends = [Trend(topic_id=7, score=0.82)]
    t.articles = []
    return t


def _service(*, llm, dedup=None, factcheck=None):
    return GeneratorService(
        _FakeTopicRepo(_topic()),
        article_repo=None,
        style_repo=_FakeStyleRepo(),
        post_repo=_FakePostRepo(),
        llm=llm,
        rag=_FakeRAGGround(),
        dedup=dedup,
        factcheck=factcheck,
        settings=Settings(dedup_max_regen_tries=2, factcheck_min_claim_chars=20),
    )


async def test_clean_draft_passes_both_gates_and_is_indexed():
    dedup = _FakeDedup(duplicate=False)
    fc = _FakeFactCheck(FactVerdict(checks=[ClaimCheck("c", supported=True)]))
    svc = _service(llm=_FakeLLM(_GOOD_JSON), dedup=dedup, factcheck=fc)
    post: GeneratedPost = await svc.generate(7)
    assert post.status == PostStatus.DRAFT
    assert post.review_notes is None
    assert dedup.added == ["1"]  # accepted post registered for future dedup


async def test_duplicate_draft_flagged_after_regen_and_not_indexed():
    dedup = _FakeDedup(duplicate=True)  # always too similar
    llm = _FakeLLM(_GOOD_JSON)
    svc = _service(llm=llm, dedup=dedup)
    post = await svc.generate(7)
    assert post.status == PostStatus.NEEDS_REVIEW
    assert post.review_notes["duplicate"]["tries"] == 2
    assert dedup.added == []  # never indexed a duplicate
    # regeneration prompt was appended on retry
    assert "REGENERATION REQUIRED" in llm.prompt


async def test_unsupported_claim_sets_needs_review():
    fc = _FakeFactCheck(
        FactVerdict(checks=[ClaimCheck("bad claim", supported=False)])
    )
    svc = _service(llm=_FakeLLM(_GOOD_JSON), dedup=_FakeDedup(duplicate=False), factcheck=fc)
    post = await svc.generate(7)
    assert post.status == PostStatus.NEEDS_REVIEW
    assert post.review_notes["unsupported_claims"] == ["bad claim"]
