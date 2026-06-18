# Run forever — this PC (systemd + Groq)

The agent runs 24/7 on this machine. The daily pipeline (10:00 IST), WhatsApp
approvals, and weekly report (Mon 09:00 IST) all fire on their own; tapping
**Approve** in WhatsApp publishes to LinkedIn.

## What makes it permanent

| Concern | How it's handled |
|---|---|
| App keeps running, restarts on crash | `systemd --user` service `linkedin-agent.service`, `Restart=always` |
| Starts on boot without you logging in | user-manager **linger** is enabled (`loginctl enable-linger empiric`) |
| DB comes back after reboot | `linkedin_agent_postgres` container `--restart=unless-stopped` + Docker enabled on boot |
| WhatsApp stays linked | `waha-dev` container `--restart=always`; session persisted in its volume (scanned once) |
| Schema always current | service `ExecStartPre` runs `alembic upgrade head` |
| LLM (no 4 GB local model) | `LLM_BACKEND=groq` — free hosted Llama, key in `.env` |

The cron lives **inside** the app (APScheduler) — there is no OS crontab. Keeping
the one process alive is the whole job, which is exactly what systemd guarantees.

> Single process on purpose: the service runs ONE uvicorn worker. The in-process
> scheduler would fire every job N times under N workers. Never add `--workers`.

## The one remaining piece: public approve links

`PUBLIC_BASE_URL` in `.env` is the URL embedded in the WhatsApp approve buttons.
It must be reachable **from your phone on cellular** (not just home wifi). A LAN IP
(`192.168.x`) only works on the same wifi. Pick one, $0, no credit card:

### Option A — Tailscale Funnel (recommended: no domain, stable URL)
```
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                       # log in (browser)
sudo tailscale funnel 8000              # serves :8000 publicly over HTTPS
tailscale funnel status                 # shows your https://<machine>.<tailnet>.ts.net URL
```
Put that `https://…ts.net` URL in `.env` as `PUBLIC_BASE_URL`, then
`systemctl --user restart linkedin-agent`.
To make the funnel itself survive reboot, run it as a service:
`sudo tailscale funnel --bg 8000` (persists), or wrap in a systemd unit.

### Option B — Cloudflare Tunnel (needs a domain on Cloudflare, ~$1–10/yr)
Create a named tunnel in Zero Trust, public hostname → `http://localhost:8000`,
then run `cloudflared tunnel run --token <TOKEN>` (wrap in a `--user` systemd unit
for boot survival). Set `PUBLIC_BASE_URL` to your subdomain.

Until a tunnel is set, approvals work only on the same wifi as this PC.

## Operating it

| Action | Command |
|---|---|
| Status | `systemctl --user status linkedin-agent` |
| Logs (live) | `journalctl --user -u linkedin-agent -f` |
| Restart (after editing .env or code) | `systemctl --user restart linkedin-agent` |
| Stop / start | `systemctl --user stop\|start linkedin-agent` |
| Disable autostart | `systemctl --user disable linkedin-agent` |
| Next scheduled runs | `journalctl --user -u linkedin-agent | grep "next run"` |
| Run pipeline now | `POST /ops/run-daily` (admin token) |
| Force weekly report | `POST /ops/weekly-report` (admin token) |

## Backing services (Docker)

```
docker ps                       # linkedin_agent_postgres (unless-stopped), waha-dev (always)
docker update --restart=unless-stopped <name>   # if a container ever loses its policy
```
Ollama was removed — generation goes through Groq. To go back fully local, set
`LLM_BACKEND=ollama` in `.env`, reinstall Ollama, and `ollama pull llama3.2:3b`.

## Gotchas

- **Groq key** lives in `.env` (`GROQ_API_KEY`). Free tier has rate limits; 3
  posts/day is well within them.
- **LinkedIn token** (`LINKEDIN_ACCESS_TOKEN`) expires ~60 days → publishes 401.
  Refresh it in `.env` and `systemctl --user restart linkedin-agent`.
- `.env` holds all secrets and is git-ignored — keep it that way.
