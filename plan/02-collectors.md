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
- [x] All 5 collectors return normalized articles (Reddit safely no-ops without creds)
- [x] Retry + timeout + rate limit on every external call (tenacity + Semaphore)
- [x] Concurrent run; one failure doesn't stop others (verified by test + live)
- [x] URL + fuzzy-title dedup working (live: 124 new then 0 new / 125 dup)
- [x] Articles stored; `/news` lists them
- [x] Committed to git

---

## Phase 2.5 — Data lifecycle (added)

Raw articles are an **ephemeral working set**, not long-term storage. Without this
a daily cron grows the DB unbounded (content text is the main cost). Strategy:

- **Slim rows** — `RetentionService` nulls the heavy `content` column once an
  article is older than `CONTENT_TTL_DAYS` (3); by then it's been scored/embedded.
- **TTL prune** — delete article rows older than `ARTICLE_TTL_DAYS` (21).
- **Seen-hash memory** — `seen_hashes` table (url_hash + last_seen, ~70 B/row,
  `SEEN_HASH_TTL_DAYS`=60) is the durable dedup key. It outlives pruned articles,
  so old news is never re-ingested even after its `articles` row is gone.

Daily cron order (wired in Phase 11): **collect → analyze → generate → prune**.
Manual ops endpoint: `POST /news/prune`. Net effect: DB stays small and flat.

- [x] `seen_hashes` durable dedup memory; collector dedups against it
- [x] `RetentionService` drops content + prunes articles + prunes hashes
- [x] verified: content 124→0 on force-drop, rows/hashes preserved; collect re-dedups to 0 new

Next: `03-trend-analyzer.md`
