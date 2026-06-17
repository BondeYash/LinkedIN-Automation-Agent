# Phase 6 — Quality Gates (Duplicate Detection + Fact Check)

## Goal
Stop bad drafts before a human ever sees them. Two gates: (1) make sure the post is not too similar to past posts, (2) make sure its claims are backed by real articles.

## Depends on
Phase 5 (need generated drafts + ChromaDB + Ollama).

## Install
No new packages — reuses `sentence-transformers`, `chromadb`, and the Ollama client already installed.

## Build steps

### Gate 1 — Duplicate detection (`app/ai/dedup.py`)
1. Embed the new draft with sentence-transformers.
2. Search ChromaDB (collection: past posts) for the closest previous post.
3. Compute **cosine similarity**. If it is above `SIMILARITY_THRESHOLD` (e.g. 0.85, set in `.env`), the post is too similar.
4. If too similar → send it back to the generator to **regenerate** (up to N tries). If still too similar after N tries, flag for human note.
5. When a post is finally accepted, add its embedding to ChromaDB so future posts get checked against it too.

### Gate 2 — Fact verification (`app/ai/factcheck.py`)
1. Split the draft body into individual **claims** (sentences/statements). Can use the LLM to list them.
2. For each claim, search ChromaDB (articles) for the most relevant source.
3. Ask the LLM (prompt `factcheck.txt`): "Does this source support this claim? Answer supported / unsupported."
4. Mark any **unsupported** claim and set the post status to `needs_review`, listing the flagged claims so the human can decide.

### Wire into the pipeline
5. After generation (Phase 5), run Gate 1 then Gate 2 automatically. Only drafts that pass (or are flagged with clear notes) move on to approval.

## Prompt files
```
app/ai/prompts/factcheck.txt
app/ai/prompts/regeneration.txt
```

## Files you create
```
app/ai/dedup.py
app/ai/factcheck.py
app/ai/prompts/factcheck.txt
app/ai/prompts/regeneration.txt
```

## Test it
1. Generate a post very similar to an existing one → dedup catches it and regenerates.
2. Put an obviously false claim in a draft → fact-check flags it as unsupported.
3. A clean, grounded draft → passes both gates with no flags.

## Done checklist
- [ ] Cosine similarity check against past posts works
- [ ] Threshold configurable in `.env`
- [ ] Too-similar drafts auto-regenerate (capped tries)
- [ ] Accepted posts added to ChromaDB
- [ ] Claims extracted and checked against sources
- [ ] Unsupported claims flagged + status set
- [ ] Committed to git

Next: `07-approval-system.md`
