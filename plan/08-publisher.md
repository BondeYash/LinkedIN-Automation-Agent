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
- [ ] `publish` endpoint rejects any non-`APPROVED` post
- [ ] Real publish stores `linkedin_post_id` + `published_at`
- [ ] Retry with backoff on transient errors only
- [ ] Failures persisted (status + error + retry count), pipeline survives
- [ ] Final text matches the approved preview exactly
- [ ] Committed to git

Next: `09-analytics.md`
