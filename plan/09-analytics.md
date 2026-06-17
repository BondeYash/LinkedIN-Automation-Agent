# Phase 9 — Analytics & Feedback Loop

## Goal
Pull engagement (likes, comments, shares, impressions) for published posts, store it as time-series, build a weekly report, and feed the winning patterns back into the generation prompt so the app keeps improving.

## Depends on
Phase 8 (posts are published and have a `linkedin_post_id`).

## Install
```bash
pip install pandas scipy
pip freeze > requirements.txt
```
- **pandas** — group/aggregate metrics for the weekly report.
- **scipy** — basic stats (deltas, simple significance) for the report.

## Build steps

1. **Analytics client** (`analyzers/analytics_client.py`): async calls to the LinkedIn metrics endpoint for a given `linkedin_post_id`. Returns likes/comments/shares/impressions. Rate-limit + retry wrapped (reuse tenacity helper from Phase 8).
2. **Analytics service** (`analyzers/analytics_service.py`):
   - For every `PUBLISHED` post, pull current metrics and **append** an `analytics` row stamped with `captured_at` (time-series — never overwrite, so trends are visible).
   - Compute `eng_rate = (likes + 2·comments + 3·shares) / impressions` per post.
3. **Weekly report** (`analyzers/weekly_report.py`): with pandas, build top posts of the week, week-over-week engagement delta, best-performing topics/hashtags/post-times. Return JSON (and optionally render to the dashboard).
4. **Feedback into prompt** (`analyzers/feedback.py`):
   - Find the top-engagement posts. Extract what they share (hook type, length band, hashtag count, post hour).
   - Write these as tuning hints into the `optimization.txt` prompt block that Phase 5's generator reads — so future drafts lean toward what worked.
5. **Repo** (`repositories/analytics_repo.py`): write `analytics` rows, query series per post, aggregate for the report.
6. **Routes** (`api/analytics.py`):
   - `GET /analytics` — current metrics + weekly report.
   - `POST /analytics/sync` — pull fresh metrics for all published posts (also called by the scheduler later).

## Files you create
```
analyzers/analytics_client.py
analyzers/analytics_service.py
analyzers/weekly_report.py
analyzers/feedback.py
repositories/analytics_repo.py
api/analytics.py
```

## Test it
1. `POST /analytics/sync` → an `analytics` row appears for each published post.
2. Sync twice with a gap → two rows per post (time-series grows, not overwritten).
3. `GET /analytics` → weekly report shows top posts + deltas.
4. After feedback runs, `optimization.txt` contains the winning patterns; a new generation reflects them.

## Done checklist
- [ ] Metrics pulled per published post
- [ ] `analytics` stored as append-only time-series with `captured_at`
- [ ] `eng_rate` computed correctly
- [ ] Weekly report: top posts + week-over-week delta
- [ ] Winning patterns written back into `optimization.txt`
- [ ] Committed to git

Next: `10-engagement-coach.md`
