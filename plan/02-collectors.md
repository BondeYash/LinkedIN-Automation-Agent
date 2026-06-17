# Phase 2 — News Collectors

## Goal
Pull the latest articles from many sources, clean them into one common shape, remove duplicates, and store them. Mostly through APIs and RSS (not scraping).

## Depends on
Phase 1 (need the `articles` table + `ArticleRepository`).

## Install
```bash
pip install feedparser httpx beautifulsoup4 praw rapidfuzz tenacity
pip freeze > requirements.txt
```
- **feedparser** — reads RSS feeds (TechCrunch, Google News).
- **httpx** — modern HTTP client, supports async; used for HN, GitHub, Dev.to.
- **beautifulsoup4** — parses HTML when only scraping is possible (rare, ToS-permitting).
- **praw** — official Reddit API wrapper (handles OAuth + rate limits).
- **rapidfuzz** — fast fuzzy text matching for near-duplicate titles.
- **tenacity** — automatic retry with backoff on flaky network calls.

> Optional (only if a source has no API/RSS and its ToS allows scraping):
> ```bash
> pip install playwright && playwright install chromium
> ```

## Build steps

1. **Add API keys to `.env`.** GitHub token, Dev.to API key, Reddit client id/secret/user-agent. Add matching fields to `Settings`.

2. **Write one collector per source** (`app/collectors/`), each inheriting `BaseCollector` and implementing `async fetch() -> list[RawArticle]`:
   - `rss_collector.py` — uses `feedparser`; takes a feed URL; works for TechCrunch + Google News.
   - `hackernews_collector.py` — uses `httpx`; reads top stories; keeps `score` (popularity signal).
   - `github_collector.py` — uses `httpx` + token; search repos created recently, sorted by stars.
   - `devto_collector.py` — uses `httpx` + api-key; top articles.
   - `reddit_collector.py` — uses `praw`; hot posts from chosen subreddits; keeps `score`.

3. **Wrap every external call** with `tenacity` retry (exponential backoff, max 3 tries) and a timeout. Add a simple rate limit (e.g. `asyncio.Semaphore`) so you respect each API's quota.

4. **Write the collector service** (`app/services/collector_service.py`). It:
   - holds a list of collectors (injected),
   - runs them all at once with `asyncio.gather(..., return_exceptions=True)` so one broken source does not kill the rest,
   - **normalizes** each raw item into the `Article` shape (`source, title, url, content, published_at, url_hash, raw_signals`),
   - **dedups**: level 1 = exact `url_hash` (sha256 of url); level 2 = fuzzy title match with `rapidfuzz` (>90% similar = same story),
   - saves new articles via `ArticleRepository`.

5. **Add an API route** (`app/api/news.py`): `POST /news/collect` to trigger collection manually, and `GET /news` to list/filter stored articles.

## Files you create
```
app/collectors/rss_collector.py
app/collectors/hackernews_collector.py
app/collectors/github_collector.py
app/collectors/devto_collector.py
app/collectors/reddit_collector.py
app/services/collector_service.py
app/api/news.py
```

## Test it
1. Unit test each collector with a **mocked** HTTP response (no real network) — confirms parsing.
2. Run `POST /news/collect` once for real — articles appear in the DB.
3. Run it again — no duplicates added (dedup works).
4. Break one source's URL on purpose — others still succeed.

## Done checklist
- [ ] All 5 collectors return normalized articles
- [ ] Retry + timeout + rate limit on every external call
- [ ] Concurrent run; one failure doesn't stop others
- [ ] URL + fuzzy-title dedup working
- [ ] Articles stored; `/news` lists them
- [ ] Committed to git

Next: `03-trend-analyzer.md`
