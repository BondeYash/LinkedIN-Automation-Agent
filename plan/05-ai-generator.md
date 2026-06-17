# Phase 5 — AI Content Generator

## Goal
Use a local AI model (Ollama) to write an original LinkedIn post for a chosen topic — headline, hook, body, CTA, hashtags, best time, and why this topic. Ground it on real articles so it stays factual.

## Depends on
Phase 3 (topics + trends) and Phase 4 (style profile).

## Install
```bash
pip install ollama chromadb
pip freeze > requirements.txt
```
- **ollama** — Python client for the local Ollama LLM server.
- **chromadb** — vector database; stores article + post embeddings for similarity search (used here for RAG, and in Phase 6 for dedup).

### Install and start Ollama itself (separate from pip)
Ollama is an app, not a pip package. Install it once on the machine:
```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
# pull a model
ollama pull llama3.1
# (or: ollama pull qwen2.5 / ollama pull mistral)
```
Confirm it runs:
```bash
ollama list
```
Set `OLLAMA_HOST` in `.env` (default `http://localhost:11434`).

## Build steps

1. **Write the Ollama client** (`app/ai/ollama_client.py`). A thin async wrapper: `generate(prompt, model)` returns text. Read the model name + host from settings. Add retry + timeout.

2. **Create prompt templates** (`app/ai/prompts/`). Plain text files with placeholders, so you can edit them without touching code:
   - `generation.txt` — the main "write a post" prompt.
   - (others added in later phases: factcheck, regeneration, etc.)

3. **Set up RAG context** (`app/ai/rag.py`). Put article embeddings into ChromaDB (collection: articles). For a given topic, fetch the top-K most relevant articles. These get pasted into the prompt as "facts to ground on" — this keeps the post truthful and current.

4. **Write the generator service** (`app/services/generator_service.py`). It:
   - takes a `topic_id`,
   - pulls the topic, its trend score, and the chosen style profile,
   - pulls top-K grounding articles via RAG,
   - fills `generation.txt` with: topic, style constraints, brand rules, grounding facts,
   - calls Ollama,
   - parses the model's **structured JSON** output:
     ```json
     { "headline": "...", "hook": "...", "body": "...", "cta": "...",
       "hashtags": ["..."], "best_post_time": "...", "topic_reason": "..." }
     ```
   - saves a `generated_posts` row with status `DRAFT`.

5. **Add API route** (`app/api/generate.py`): `POST /generate` with a `topic_id` → returns the draft.

## Files you create
```
app/ai/ollama_client.py
app/ai/rag.py
app/ai/prompts/generation.txt
app/services/generator_service.py
app/api/generate.py
```

## Test it
1. Make sure Ollama is running and a model is pulled.
2. `POST /generate` with a real topic id → you get a full draft with all fields.
3. Check the draft mentions facts from the grounding articles (not made-up claims).
4. Re-run with a different topic → different, relevant post.

## Done checklist
- [x] Ollama installed (user-space `~/.local/bin/ollama`, no sudo), `llama3.1` pulled, client works
- [x] Prompt template in a file (editable) — `app/ai/prompts/generation.txt`
- [x] RAG pulls relevant articles from ChromaDB — `app/ai/rag.py` (embedded PersistentClient, reuses our embedder)
- [x] Generator returns valid structured JSON — robust `parse_post_json` (fences/prose tolerant, key-validated)
- [x] Draft saved with status DRAFT
- [x] Committed to git

## Notes (implementation)
- `app/ai/ollama_client.py` — async wrapper behind an `LLMClient` Protocol (fake drives tests),
  JSON mode via Ollama `format="json"`, transient retry + timeout from settings.
- `app/ai/rag.py` — embedded Chroma (no separate server); `index()` upserts article vectors,
  `query(topic)` returns top-K `GroundingFact`. Generator falls back to `topic.articles` if empty.
- `app/services/generator_service.py` — topic + trend + style + RAG facts → prompt → LLM → parse → DRAFT.
- Closed the Phase 4 stub: `OllamaStyleLabeler` added (short labels only, never copied text).
- 6 new tests (parser + full flow with fakes); full suite 27 green; app builds with router mounted.
- **Live-verified**: `POST /generate {topic_id:117}` → full grounded DRAFT (headline/hook/body/cta/
  hashtags/reason) saved id=2, ~2m29s on CPU (no GPU). Facts traced to the topic's RAG articles.
- CPU notes: raised `ollama_timeout_seconds` to 600 (cold model load is slow) and capped
  `ollama_num_predict=700` to bound latency. Warm generation ~2.5 min for a full post.

Next: `06-quality-gates.md`
