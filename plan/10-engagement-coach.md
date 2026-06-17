# Phase 10 — Profile & Engagement Coach

## Goal
Self-audit **your own** LinkedIn account: pull all your recent posts, tag which came from this app vs posted manually, measure engagement, mine what drives it, and output personalized improvement tips and per-post rewrites. Reads only your own account via your OAuth — no scraping.

## Depends on
Phase 9 (analytics in place; `publishing_history` has `linkedin_post_id` for provenance).

## Install
```bash
pip install scikit-learn statsmodels
pip freeze > requirements.txt
```
- **scikit-learn** — linear/logistic regression for pattern mining.
- **statsmodels** — t-test (app vs manual) and regression with p-values.

## Key formulas (from architecture)
```
source   = "app"  if linkedin_post_id ∈ publishing_history  else "manual"
eng_rate = (likes + 2·comments + 3·shares) / impressions
lift%    = (avg_eng_app − avg_eng_manual) / avg_eng_manual · 100   # t-test for significance
eng_rate ≈ w·[length, post_hour, day_of_week, hashtag_count,
              has_media, hook_type, emoji_count, has_question_cta]
```

## Build steps

1. **Account sync** (`analyzers/coach_sync.py`): pull your recent account posts via your OAuth. For each, store an `account_posts` row: `linkedin_post_id`, text, `posted_at`, `media_type`, `length`, `hashtag_count`, `source` (app/manual via the provenance check), `eng_rate`.
2. **App-impact report** (`analyzers/coach_impact.py`): split posts by `source`, compute `avg_eng_app` vs `avg_eng_manual`, the `lift%`, and a t-test p-value for significance.
3. **Pattern mining** (`analyzers/coach_patterns.py`): featurize each post (length, hour, day, hashtags, has_media, hook_type, emoji_count, has_question_cta), regress `eng_rate` on them. Fitted weights → human-readable findings (e.g. "8am posts +40%", "3 hashtags beat 10"). Save to `engagement_insights` (`metric`, `finding`, `confidence`).
4. **Improvement tips** (`analyzers/coach_tips.py`): turn the strongest insights into concrete, ranked tips. Save to `improvement_tips`.
5. **Per-post diagnosis** (`analyzers/coach_diagnose.py`): for one post, explain why it under/over-performed (using the mined weights) and produce an LLM rewrite via the `coach_diagnosis.txt` prompt.
6. **Trend correlation:** Pearson between `trend_score` (from the original draft) and final engagement, to see if chasing trends actually paid off.
7. **Feedback:** push the mined weights into the §6 generation prompt (extends Phase 9's loop) so generation biases toward your audience.
8. **Routes** (`api/coach.py`):
   - `POST /coach/sync` — pull account posts + metrics.
   - `GET /coach/audit` — full account report.
   - `GET /coach/app-impact` — app-suggested vs manual lift %.
   - `GET /coach/insights` — mined patterns.
   - `GET /coach/tips` — improvement suggestions.
   - `GET /coach/post/{id}` — per-post diagnosis + rewrite.

## Files you create
```
analyzers/coach_sync.py
analyzers/coach_impact.py
analyzers/coach_patterns.py
analyzers/coach_tips.py
analyzers/coach_diagnose.py
repositories/coach_repo.py
api/coach.py
prompts/coach_diagnosis.txt
```

## Test it
1. `POST /coach/sync` → `account_posts` populated; app-published posts tagged `source=app`, others `manual`.
2. `GET /coach/app-impact` → shows lift % + p-value.
3. `GET /coach/insights` → at least a few mined findings with confidence.
4. `GET /coach/tips` → ranked, concrete tips.
5. `GET /coach/post/{id}` → diagnosis + a rewrite of that post.

## Done checklist
- [ ] Account posts synced + provenance tagged (app vs manual)
- [ ] App-impact lift % + t-test
- [ ] Pattern mining → `engagement_insights`
- [ ] Improvement tips generated + ranked
- [ ] Per-post diagnosis + LLM rewrite
- [ ] Mined weights feed back into generation prompt
- [ ] Committed to git

Next: `11-scheduler-api-tests.md`
