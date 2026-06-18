# PC-off-proof cron via GitHub Actions

Your PC can be **fully powered off** and the daily/weekly jobs still run — GitHub
runs them in the cloud on a schedule. State lives in a free cloud Postgres; drafts
are emailed to you.

```
GitHub Actions (cron)  →  runs scripts/run_job.py  →  Neon Postgres (state)
        ├─ daily  10:00 IST : collect → analyze → generate (Groq) → email you
        └─ weekly Mon 09:00 : analytics sync + weekly report
```

What does **not** survive PC-off: the WhatsApp one-tap approve and live publish —
those need the always-on web app + WAHA. In this mode the cron **produces** posts
and emails them; you approve/publish from the dashboard when the app is next up
(it reads the same Neon database). To get the full one-tap flow 24/7 you'd need an
always-on host (see `RUN_FOREVER.md` / a small VPS).

---

## 1. Free cloud Postgres (Neon — no credit card)

1. Sign up at **neon.tech** (free tier, no card).
2. Create a project → copy the connection string.
3. Convert it to the app's driver format — add `+psycopg`:
   ```
   postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
   ```
   This is your `DATABASE_URL` secret. (Alternative: Supabase, also no card.)

## 2. Gmail App Password (for the email channel)

1. Enable 2-Step Verification on your Google account.
2. Google Account → Security → **App passwords** → generate one for "Mail".
3. That 16-char password is `SMTP_PASSWORD`; your address is `SMTP_USER` and
   `NOTIFY_TO_EMAIL` (where drafts are sent).

## 3. Add the GitHub repo secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**.
Add each:

| Secret | Value |
|---|---|
| `DATABASE_URL` | the Neon `postgresql+psycopg://…?sslmode=require` string |
| `GROQ_API_KEY` | your Groq key |
| `SECRET_KEY` | any long random string (signs the approve-link tokens) |
| `PUBLIC_BASE_URL` | your app URL for approve links (e.g. the Tailscale `https://…ts.net`); used when the app is later reachable |
| `LINKEDIN_ACCESS_TOKEN` | member token |
| `LINKEDIN_AUTHOR_URN` | `urn:li:person:…` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASSWORD` | the App Password from step 2 |
| `NOTIFY_TO_EMAIL` | inbox to receive drafts (can be the same address) |

(`SMTP_HOST`/`SMTP_PORT`/`LLM_BACKEND` etc. are already set in the workflow file.)

## 4. Push + test

The workflow file is at `.github/workflows/agent-cron.yml`. Once it's on the
default branch:

1. Repo → **Actions** → "LinkedIn Agent Cron" → **Run workflow** → pick `daily` →
   Run. This is a manual trigger (`workflow_dispatch`) — same code as the cron.
2. Watch the run. On success you get an email with the generated draft(s), and the
   posts are written to Neon.
3. The scheduled runs then fire automatically: **10:00 IST daily**, **09:00 IST
   Monday** (weekly). No PC required.

## Notes

- **Cron timing.** GitHub cron is UTC and can be delayed several minutes under
  load — fine for a content job. Times: `30 4 * * *` = 10:00 IST, `30 3 * * 1` =
  09:00 IST Monday.
- **First run is slow.** Installing deps (incl. the embedding libs) takes a few
  minutes; the 25-min job timeout covers it. Quality gates are disabled in CI
  (`QUALITY_GATES_ENABLED=false`) since dedup/fact-check need a vector store.
- **Free minutes.** Public repos: unlimited Actions minutes. Private repos: 2,000
  min/month free — a daily ~5-min job is well within that.
- **One DB, two runners.** Point your local app at the SAME Neon `DATABASE_URL`
  and the dashboard/approve/publish operate on the cron's output seamlessly.
