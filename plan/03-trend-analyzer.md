# Phase 3 — Trend Analyzer

## Goal
Look at all stored articles, group ones about the same story, and give each topic a **trend score** so the best topics rise to the top.

## Depends on
Phase 2 (need articles in the DB).

## Install
```bash
pip install sentence-transformers scikit-learn numpy
pip freeze > requirements.txt
```
- **sentence-transformers** — turns text into vectors (embeddings) so we can measure meaning-similarity.
- **scikit-learn** — clustering (DBSCAN/KMeans) and simple regression later.
- **numpy** — math on vectors/arrays.

> First run downloads a small model (e.g. `all-MiniLM-L6-v2`). Needs internet once, then cached.

## Build steps

1. **Write an embedding helper** (`app/ai/embeddings.py`). Load the sentence-transformer model once (reuse it). Function `embed(texts) -> vectors`. Run heavy work in a threadpool so it does not block async code.

2. **Cluster articles into topics** (`app/analyzers/trend_analyzer.py`, part 1). Embed article titles+summaries, then run **DBSCAN** with cosine distance. Each cluster = one `Topic` (same story from many sources). DBSCAN is good here because you do not know how many topics exist each day.

3. **Compute the trend score** (part 2). For each topic, combine signals into one number. Normalize each signal to 0–1 first.
   ```
   trend_score = w1·popularity + w2·recency + w3·tech_rel + w4·biz_impact + w5·audience_rel
   ```
   - **popularity** = `log(1 + sum of engagement)` (HN score + GitHub stars + how many sources mention it). Log stops one viral item dominating.
   - **recency** = `exp(-λ · hours_old)`, with `λ = ln(2)/half_life` (e.g. half_life = 24h). Newer = higher.
   - **tech / business / audience relevance** = cosine similarity between the topic vector and reference theme vectors you define (your target subjects).
   - Start with simple weights (e.g. all signals matter), tune later from analytics (Phase 9/10).

4. **Store results.** Write `Topic` rows and `Trend` rows (score + each component + run date) via repositories.

5. **Add API routes** (`app/api/trends.py`): `POST /trends/analyze` to run the analyzer, `GET /trends` to list topics ranked by score.

## Files you create
```
app/ai/embeddings.py
app/analyzers/trend_analyzer.py
app/api/trends.py
```

## Test it
1. Unit test the scoring math with fixed numbers (e.g. older article gets lower recency).
2. Run `POST /trends/analyze` after collecting news.
3. `GET /trends` returns topics sorted high → low score.
4. Check that articles about the same event landed in the same topic cluster.

## Done checklist
- [ ] Embeddings generated and reused (model loaded once)
- [ ] Articles cluster into topics (DBSCAN)
- [ ] Each signal normalized; trend_score computed
- [ ] Topics + trends stored
- [ ] `/trends` returns ranked list
- [ ] Committed to git

Next: `04-style-intelligence.md`
