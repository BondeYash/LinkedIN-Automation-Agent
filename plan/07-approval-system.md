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
- [ ] Login + JWT protect routes
- [ ] Passwords hashed (bcrypt)
- [ ] All four actions change status + log audit
- [ ] Dashboard lists pending with score + flags + buttons
- [ ] Email, Teams, Sheets notifications send with links
- [ ] Every state change recorded
- [ ] Committed to git

Next: `08-publisher.md`
