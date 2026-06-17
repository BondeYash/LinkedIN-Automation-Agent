# Phase 8 — LinkedIn Publisher

## Goal
Take an **APPROVED** post and publish it to LinkedIn through the official API, store the returned LinkedIn post id, and retry safely if the call fails. No post that is not `APPROVED` may ever publish.

## Depends on
Phase 7 (posts can reach `APPROVED` status).

## Install
```bash
pip install tenacity httpx
pip freeze > requirements.txt
```
- **tenacity** — retry with exponential backoff on transient failures.
- **httpx** — async HTTP client for the LinkedIn API calls.

## LinkedIn setup (one time)
1. Create a LinkedIn Developer app, request the **Share on LinkedIn** / Posts product.
2. Run the OAuth2 authorization-code flow once to get an access token (and refresh token) for your member account.
3. Put the token + your member URN in `.env`:
```
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_AUTHOR_URN=urn:li:person:xxxx
```

## Build steps

1. **Base interface** (`core/base.py`): confirm `BasePublisher` ABC exists with `async def publish(post) -> PublishResult`.
2. **LinkedIn client** (`publishers/linkedin_client.py`): thin async wrapper over the UGC/Posts endpoint. Builds the JSON body (author URN, text, visibility = PUBLIC). Handles auth header. One method: `create_post(text) -> linkedin_post_id`.
3. **Publisher** (`publishers/linkedin_publisher.py`) implements `BasePublisher`:
   - **Guard first:** re-read the post from the repo; if status != `APPROVED`, raise — never trust the caller.
   - Assemble final text (headline + hook + body + cta + hashtags) the same way the dashboard previewed it.
   - Wrap `create_post` in `@retry` (tenacity): exponential backoff, max ~5 tries, retry only transient (5xx, timeout, 429), give up on 4xx auth errors.
   - On success: write a `publishing_history` row (`linkedin_post_id`, `status=PUBLISHED`, `published_at`, `retries`), set post status to `PUBLISHED`.
   - On final failure: write `publishing_history` with `status=FAILED` and the `error` text; leave the post so it can be retried later. Never crash the pipeline.
4. **Publish route** (`api/publishing.py`): `POST /publish/{post_id}` — guarded; calls the publisher service. Returns the LinkedIn post id or the failure reason.
5. **Repo** (`repositories/publishing_repo.py`): create/read `publishing_history` rows, fetch latest attempt per post.

## Files you create
```
publishers/linkedin_client.py
publishers/linkedin_publisher.py
repositories/publishing_repo.py
api/publishing.py
```

## Test it
1. Try `POST /publish/{id}` on a `DRAFT` post → rejected (guard works).
2. Approve a post, publish → a real LinkedIn post id comes back, `publishing_history` row written, post status `PUBLISHED`.
3. Force a transient error (point client at a bad URL / mock a 503) → see retries in logs, then a `FAILED` row with the error.
4. Token expiry → clear 4xx failure, no infinite retry.

## Done checklist
- [x] `publish` endpoint rejects any non-`APPROVED` post — `POST /publish/{id}` (editor JWT) + publisher re-reads & guards (`NotApproved`→409, `PostNotFound`→404)
- [x] Real publish stores `linkedin_post_id` + `published_at` — `publishing_history` row, post status → `PUBLISHED`
- [x] Retry with backoff on transient errors only — tenacity `AsyncRetrying` (5xx/timeout/429), 4xx fails fast; `publish_max_tries`
- [x] Failures persisted (status + error + retry count), pipeline survives — FAILED row, post left `APPROVED` for retry, never raises
- [x] Final text matches the approved preview exactly — `render_post_text` (headline+hook+body+cta+hashtags), same order as dashboard
- [x] Committed to git

## Notes (implementation)
- **Client** (`app/publishers/linkedin_client.py`): thin async httpx wrapper over the
  UGC Posts endpoint (`/v2/ugcPosts`). Official API only — no scraping. Builds the PUBLIC
  ShareContent body (author URN + text), Bearer auth, `X-Restli-Protocol-Version: 2.0.0`.
  Reads the new id from `X-RestLi-Id` header (falls back to body `id`). Raises `httpx`
  errors verbatim; `LinkedInAuthError` if token/URN missing.
- **Publisher** (`app/publishers/linkedin_publisher.py`) implements `BasePublisher`:
  re-reads the post (never trusts the caller), guards `status == APPROVED`, assembles the
  text via `render_post_text`, retries the client with tenacity `AsyncRetrying` (shared
  `is_transient` predicate from `utils/http`) counting attempts, then writes a
  `publishing_history` row + an `audit_logs` row and flips status. On final failure: FAILED
  row, post stays APPROVED, returns `PublishResult(ok=False)` — pipeline never crashes.
- **Route** (`app/api/publishing.py`): `POST /publish/{post_id}`, editor/admin only; maps
  guard errors to 404/409; transient publish failure returns 200 `ok:false`.
- No migration: `poststatus` already has PUBLISHED/FAILED and `publishstatus` exists from
  the Phase 1 initial migration; `PublishingRepository` added in Phase 7.
- Config: `linkedin_access_token`, `linkedin_author_urn`, `linkedin_api_base`,
  `linkedin_timeout_seconds`, `publish_max_tries`. Deps already present: tenacity, httpx.
- **Tested** (8 new, fakes, no network/DB): text-order match + empty-skip; guard refuses
  non-APPROVED + unknown post; success writes history & PUBLISHED; transient retried then
  succeeds (retries counted); exhausted transient → FAILED row, stays APPROVED; 4xx fails
  fast (1 call) despite max_tries=5. Full suite 61 green.

Next: `09-analytics.md`
