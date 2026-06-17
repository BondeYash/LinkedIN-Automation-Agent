# Phase 4 — LinkedIn Content Intelligence (Style Learning)

## Goal
Learn the *writing style* of good LinkedIn posts (yours/approved ones) — hooks, CTAs, length, emoji use, hashtag habits — and save it as a reusable "style profile". We learn patterns, **never copy** content.

## Depends on
Phase 1 (need `style_profiles` table). Can be built in parallel with Phase 2–3.

## Install
No new packages needed (uses the LLM client from Phase 5 if available, plus simple text stats). If you want quick text stats now:
```bash
pip install textstat
pip freeze > requirements.txt
```
- **textstat** — easy readability/sentence-length metrics. Optional helper.

## Build steps

1. **Collect sample text.** Gather your previously approved posts (or a small seed set of reference posts you legally have). Store raw text rows you can read from.

2. **Extract measurable features** (`app/analyzers/style_analyzer.py`). Compute simple numbers directly from text:
   - average paragraph size, average sentence length,
   - emoji count/density,
   - hashtag count and placement,
   - formatting use (bullets, line breaks, ALL-CAPS hooks).

3. **Extract descriptive features with the LLM** (uses Ollama — if not ready yet, stub this and fill in after Phase 5). Ask the model to label: hook style, CTA style, storytelling pattern. Get back short labels, not copied text.

4. **Save a Style Profile.** Combine number-features + label-features into one JSON and store in `style_profiles` (with a name and source). This JSON becomes a set of *constraints* the generator must follow later.

5. **Add API route** (optional): `POST /style/analyze` to (re)build a profile from current samples, `GET /style` to view profiles.

## Files you create
```
app/analyzers/style_analyzer.py
app/api/style.py        (optional)
```

## Test it
1. Feed in 3–5 sample posts.
2. Confirm the saved profile has sensible numbers (e.g. average sentence length looks right).
3. Confirm it stores only patterns/labels — no full copied sentences from sources.

## Done checklist
- [x] Number-features extracted correctly (lengths, sentences, emoji, hashtags, hooks, bullets)
- [x] LLM label-features added (stubbed via `NullStyleLabeler`; Phase 5 swaps in Ollama)
- [x] Style profile saved as JSON in DB (upsert by name)
- [x] No copied content stored — only aggregate numbers + ratios (test asserts no raw text)
- [x] Committed to git

## Notes (implementation)
- `app/analyzers/style_features.py` — pure stats, no deps (skipped optional `textstat`).
- `app/analyzers/style_labeler.py` — `StyleLabeler` Protocol + `NullStyleLabeler` stub
  so Phase 5 plugs the Ollama labeler in without touching the analyzer.
- `app/analyzers/style_analyzer.py` — combines numbers + labels, upserts `StyleProfile`.
- `seed/sample_posts.py` — 5 generic reference posts (written for this project, not copied).
- API: `POST /style/analyze` (body posts or seed fallback), `GET /style`.
- live: built `default` from 5 seed posts — ~41 words avg, 2.4 hashtags, all trailing,
  40% bullets; 6 new tests, full suite green.

Next: `05-ai-generator.md`
