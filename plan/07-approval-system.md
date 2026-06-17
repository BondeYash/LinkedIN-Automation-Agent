# Phase 7 — Approval System

## Goal
A human must approve every post before it can be published. Build the dashboard, login security, and notifications (email, Teams, Google Sheets) with approve / reject / edit / regenerate actions.

## Depends on
Phase 6 (drafts that passed the quality gates).

## Install
```bash
pip install "python-jose[cryptography]" "passlib[bcrypt]" python-multipart \
            google-api-python-client google-auth google-auth-oauthlib gspread jinja2
pip freeze > requirements.txt
```
- **python-jose** — create/verify JWT login tokens.
- **passlib[bcrypt]** — hash passwords safely.
- **python-multipart** — needed for form/login posts in FastAPI.
- **google-api-python-client + google-auth + google-auth-oauthlib** — Gmail API + Google auth.
- **gspread** — easy Google Sheets read/write.
- **jinja2** — render the dashboard HTML pages.

## Build steps

### Auth
1. **Security helpers** (`app/core/security.py`): hash/verify passwords, create JWT, decode JWT.
2. **Auth route** (`app/api/auth.py`): `POST /auth/login` → returns a JWT. A `get_current_user` dependency protects other routes.

### Approval flow
3. **Approval states.** A post moves: `DRAFT → PENDING → APPROVED | REJECTED | EDITED → REGENERATE`. Add a service (`app/services/approval_service.py`) that changes status, records who/when in `approvals`, and writes an `audit_logs` row each time.
4. **Approval routes** (`app/api/approval.py`):
   - `GET /approvals` — list pending drafts with topic, trend score, hashtags, suggested time, and any fact-check flags.
   - `POST /approvals/{id}/approve`
   - `POST /approvals/{id}/reject`
   - `POST /approvals/{id}/edit` (human edits text)
   - `POST /approvals/{id}/regenerate` (send back to generator)

### Dashboard
5. **Dashboard pages** (`app/api/admin.py` + `templates/`). Jinja2 pages showing: pending approvals, trend score, draft preview, flags, and the four action buttons. Keep it simple server-rendered HTML first; a fancy frontend can come later.

### Notifications (each implements `BaseNotifier`)
6. **Email** (`app/notifications/email_notifier.py`) — Gmail API. Sends the draft preview plus signed approve/reject/regenerate links (one-click, token-protected so only the right person can act).
7. **Teams** (`app/notifications/teams_notifier.py`) — posts an adaptive card to a Teams webhook with the preview + links.
8. **Google Sheets** (`app/notifications/sheets_notifier.py`) — appends each draft as a row; a status column the human edits is read back to drive approval.
9. **Notification service** — after a draft becomes `PENDING`, fan out to all enabled channels and log each send in `notifications`.

## Files you create
```
app/core/security.py
app/api/auth.py
app/api/approval.py
app/api/admin.py
app/services/approval_service.py
app/notifications/email_notifier.py
app/notifications/teams_notifier.py
app/notifications/sheets_notifier.py
templates/...
```

## Test it
1. Log in → get a JWT; protected routes reject missing/invalid tokens.
2. A new draft shows up under `GET /approvals` and on the dashboard.
3. Click approve → status becomes `APPROVED`, an `approvals` row + `audit_logs` row are written.
4. Email/Teams/Sheets notification arrives with working links.
5. Reject and regenerate also work and are logged.

## Done checklist
- [x] Login + JWT protect routes — `POST /auth/login` → bearer JWT; `get_current_user`/`require_role` deps
- [x] Passwords hashed (bcrypt) — `app/core/security.py` (already from Phase 1; JWT added here)
- [x] All four actions change status + log audit — approve/reject/edit/regenerate write `approvals` + `audit_logs`
- [x] Dashboard lists pending with score + flags + buttons — `GET /admin`, `templates/dashboard.html`
- [x] Email, Teams, Sheets notifications send with links — `app/notifications/*` (log fallback offline)
- [x] Every state change recorded — `audit_logs` row per transition
- [x] Committed to git

## Notes (implementation)
- **Auth** (`security.py` + `api/auth.py` + `deps.py`): HS256 JWT (`create/decode_access_token`),
  `HTTPBearer` → `get_current_user` (active-user check), `require_role(...)` factory (ADMIN always
  allowed). `POST /auth/login` takes the OAuth2 password form; `GET /auth/me` verifies a token.
- **Approval** (`services/approval_service.py` + `api/approval.py`): `submit` → PENDING (+ notify),
  `approve/reject/edit/regenerate`; each writes an `approvals` row + an `audit_logs` row, guarded by a
  status check (`InvalidTransition` → 409, `PostNotFound` → 404). Editors + admins only.
- **One-click links**: signed, expiring *action* tokens (`create_action_token`) → `GET /approvals/action`
  acts without a login (token authenticates intent). Distinct token `type` from access tokens.
- **Notifications** (`app/notifications/`): `Notifier` protocol; `LogNotifier` (always-on offline
  fallback) + Email (Gmail API), Teams (webhook card), Sheets (gspread) — each lazy-imported and skipped
  unless configured. `NotificationService.dispatch` fans out, isolates per-channel failures, records one
  `notifications` row (SENT/FAILED) each. Channels chosen via `notification_channels` env (default `log`).
- New: `NotificationChannel.LOG` enum value (migration `029aed573f60`, Postgres `ADD VALUE`).
- Deps added: python-jose, python-multipart, jinja2, google-api-python-client/auth/oauthlib, gspread.
- **Live-verified** (TestClient, real DB): no-auth→401, bad login→401, login→200, `/auth/me`, queue lists
  3 drafts, submit→pending, approve→approved, re-approve→409, one-click reject→200, bad token→401,
  dashboard→200; `approvals`/`audit_logs`/`notifications` rows written. 14 new tests; full suite 53 green.

Next: `08-publisher.md`
