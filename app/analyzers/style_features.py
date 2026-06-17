"""Quantitative style features — pure text stats, no deps, no DB, no LLM.

Everything here is a *number* or *ratio* derived from sample post text. We never
keep the text itself, only aggregate measurements — so a saved style profile
describes patterns ("short sentences, 3 hashtags, sparing emoji") and can never
leak a copied sentence.

Kept separate from the analyzer so the math is unit-testable with fixed strings.
"""

from __future__ import annotations

import re
import unicodedata
from statistics import mean

_SENTENCE_RE = re.compile(r"[.!?]+(?:\s|$)")
_WORD_RE = re.compile(r"\b[\w']+\b")
_HASHTAG_RE = re.compile(r"#\w+")
_BULLET_RE = re.compile(r"^\s*[-*•·▪►]|\d+[.)]\s", re.MULTILINE)
_ALLCAPS_RE = re.compile(r"\b[A-Z]{3,}\b")


def _is_emoji(ch: str) -> bool:
    # Pictographs, symbols and regional indicators report as "So"/"Sk" in the
    # symbol category, plus the common emoji blocks above the BMP.
    if ch in "‍️":  # ZWJ / variation selector — emoji glue
        return True
    code = ord(ch)
    if 0x1F000 <= code <= 0x1FAFF or 0x2600 <= code <= 0x27BF:
        return True
    return unicodedata.category(ch) in {"So", "Sk"}


def count_emojis(text: str) -> int:
    return sum(1 for ch in text if _is_emoji(ch))


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def post_features(text: str) -> dict:
    """Numeric features for a single post."""
    words = _words(text)
    sentences = _sentences(text)
    paragraphs = _paragraphs(text)
    hashtags = _HASHTAG_RE.findall(text)
    emojis = count_emojis(text)
    word_count = len(words)
    first = _first_line(text)

    # Hashtags "at the end" if they sit in the final paragraph.
    last_para = paragraphs[-1] if paragraphs else ""
    hashtags_trailing = bool(hashtags) and len(_HASHTAG_RE.findall(last_para)) == len(hashtags)

    return {
        "char_count": len(text),
        "word_count": word_count,
        "sentence_count": len(sentences),
        "avg_sentence_words": (word_count / len(sentences)) if sentences else 0.0,
        "paragraph_count": len(paragraphs),
        "avg_paragraph_words": (word_count / len(paragraphs)) if paragraphs else 0.0,
        "hashtag_count": len(hashtags),
        "emoji_count": emojis,
        "emoji_density_per_100w": (emojis / word_count * 100) if word_count else 0.0,
        "has_bullets": bool(_BULLET_RE.search(text)),
        "hashtags_trailing": hashtags_trailing,
        "hook_is_question": first.endswith("?"),
        "hook_has_allcaps": bool(_ALLCAPS_RE.search(first)),
    }


def aggregate(texts: list[str]) -> dict:
    """Average the per-post numbers and turn the booleans into 0–1 ratios."""
    posts = [post_features(t) for t in texts if t and t.strip()]
    if not posts:
        return {"sample_size": 0}

    def avg(key: str) -> float:
        return round(mean(p[key] for p in posts), 2)

    def ratio(key: str) -> float:
        return round(sum(1 for p in posts if p[key]) / len(posts), 2)

    return {
        "sample_size": len(posts),
        "avg_char_count": avg("char_count"),
        "avg_word_count": avg("word_count"),
        "avg_sentence_words": avg("avg_sentence_words"),
        "avg_paragraph_count": avg("paragraph_count"),
        "avg_paragraph_words": avg("avg_paragraph_words"),
        "avg_hashtag_count": avg("hashtag_count"),
        "avg_emoji_count": avg("emoji_count"),
        "emoji_density_per_100w": avg("emoji_density_per_100w"),
        "bullet_usage_ratio": ratio("has_bullets"),
        "hashtags_trailing_ratio": ratio("hashtags_trailing"),
        "question_hook_ratio": ratio("hook_is_question"),
        "allcaps_hook_ratio": ratio("hook_has_allcaps"),
    }
