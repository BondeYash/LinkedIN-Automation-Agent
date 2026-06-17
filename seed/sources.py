"""Static list of content sources the collectors (Phase 2) pull from.

Kept in code (not a DB table) because it changes rarely and belongs in version
control. Each entry: a collector `kind` and its endpoint/feed.
"""

from __future__ import annotations

DEFAULT_SOURCES: list[dict[str, str]] = [
    {"kind": "rss", "name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"kind": "rss", "name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
    {"kind": "rss", "name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"kind": "hackernews", "name": "Hacker News Top", "url": "https://hacker-news.firebaseio.com/v0/topstories.json"},
    {"kind": "github", "name": "GitHub Trending", "url": "https://api.github.com/search/repositories"},
    {"kind": "devto", "name": "Dev.to", "url": "https://dev.to/api/articles"},
    {"kind": "reddit", "name": "r/programming", "url": "https://www.reddit.com/r/programming/top.json"},
]
