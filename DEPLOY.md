# Deploy — run the agent forever (Oracle Cloud + Cloudflare Tunnel)

Goal: the daily pipeline, WhatsApp approvals, and weekly report run **24/7 with no
laptop involved**, and auto-recover after reboot, crash, or power loss.

How it works:
- The whole stack runs as one Docker Compose project on an **always-on VM**.
- Every service has `restart: unless-stopped`; the Docker daemon is enabled on
  boot ⇒ the stack auto-resumes after any restart. The VM never powers off, so it
  runs even when **all your own devices are off**.
- **cloudflared** gives a public HTTPS URL for the approve links — **no inbound
  ports** opened on the VM except SSH.

The scheduler is *inside* the app (APScheduler), so there is **no OS crontab** to
configure — keeping the container alive is the whole job.

---

## 1. Create the VM (Oracle Cloud — Always Free)

1. Sign up at <https://cloud.oracle.com> (free tier, no charge for Ampere A1).
2. **Compute → Instances → Create instance.**
   - Image: **Ubuntu 22.04**.
   - Shape: **VM.Standard.A1.Flex** (Ampere/ARM). Set **4 OCPU / 24 GB RAM**
     (the full always-free Ampere allowance — needed for Ollama).
   - Add your SSH public key.
3. **Networking / Security List:** leave only **22 (SSH)** open inbound. Nothing
   else is needed — cloudflared dials *out*.
4. Note the public IP. SSH in:
   ```
   ssh ubuntu@<VM_PUBLIC_IP>
   ```

> ARM note: every image in the stack (postgres, ollama, chromadb, waha,
> cloudflared, python) has an arm64 build, so it runs natively on Ampere.

## 2. Install Docker

```
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker          # apply group without re-login
sudo systemctl enable --now docker   # <-- this is what makes it survive reboot
```

## 3. Get the code + env

```
git clone <YOUR_REPO_URL> linkedin-agent && cd linkedin-agent
cp .env.prod.example .env
nano .env
```
Fill in: `SECRET_KEY`, `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN`,
`WAHA_API_KEY`, `WHATSAPP_RECIPIENT`, and `PUBLIC_BASE_URL` /
`CLOUDFLARE_TUNNEL_TOKEN` (next step).

## 4. Create the Cloudflare tunnel

1. Add a domain to Cloudflare (any domain you control; free plan is fine).
2. **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared.**
3. Name it, then copy the **tunnel token** (the long string in the install
   command) → paste into `.env` as `CLOUDFLARE_TUNNEL_TOKEN`.
4. **Public Hostname** for the tunnel:
   - Subdomain/domain: e.g. `linkedin-agent.yourdomain.com`
   - Service: **HTTP** → `app:8000`
5. Set `PUBLIC_BASE_URL=https://linkedin-agent.yourdomain.com` in `.env`
   (no trailing slash). This is what the WhatsApp approve links use.

## 5. Launch

```
docker compose -f docker-compose.prod.yml up -d --build
```
First boot pulls the LLM (`ollama-pull` one-shot, a few minutes). Watch:
```
docker compose -f docker-compose.prod.yml logs -f ollama-pull app cloudflared
```
Health check through the tunnel:
```
curl https://linkedin-agent.yourdomain.com/health   # -> {"status":"ok"}
```

## 6. Link WhatsApp (one time)

WAHA has no public port. Scan the QR once over an **SSH tunnel** (secure, nothing
exposed):
```
# on your laptop:
ssh -L 3000:localhost:3000 ubuntu@<VM_PUBLIC_IP>
```
Open <http://localhost:3000/dashboard>, start/inspect session `linkedin-agent`,
scan the QR with the WhatsApp account `918849552884`. The session is saved to the
`waha_sessions` volume and auto-resumes on every restart — **scan once, ever**.

## 7. Smoke test end-to-end

Get an admin token, then trigger a run (replace host):
```
BASE=https://linkedin-agent.yourdomain.com
TOKEN=$(curl -s -X POST $BASE/auth/login -d 'username=admin&password=...' | jq -r .access_token)
curl -s -X POST $BASE/ops/run-daily -H "Authorization: Bearer $TOKEN" | jq
```
You should get 3 WhatsApp messages. Tap **Approve** → it publishes to LinkedIn.
Force the weekly report with `POST $BASE/ops/weekly-report`.

## 8. Prove it survives reboot

```
sudo reboot
```
Reconnect after a minute:
```
docker compose -f docker-compose.prod.yml ps   # all services Up again, untouched
```
Docker started on boot → `restart: unless-stopped` brought every container back →
the in-process scheduler re-armed (next daily 10:00 IST, next weekly Mon 09:00 IST).
Nothing to do. It now runs forever.

---

## Operations cheat-sheet

| Action | Command |
|---|---|
| Logs | `docker compose -f docker-compose.prod.yml logs -f app` |
| Restart app only | `docker compose -f docker-compose.prod.yml restart app` |
| Update to new code | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Stop everything | `docker compose -f docker-compose.prod.yml down` |
| DB backup | `docker exec linkedin_agent_postgres pg_dump -U postgres linkedin_agent > backup.sql` |
| Next scheduled runs | `docker compose -f docker-compose.prod.yml logs app | grep "next run"` |

## Notes / gotchas

- **Single process on purpose.** The app runs one uvicorn process (no `--workers`).
  The APScheduler cron lives in-process; multiple workers would fire each job N
  times. The entrypoint runs `alembic upgrade head` before serving.
- **Token expiry.** `LINKEDIN_ACCESS_TOKEN` expires (~60 days). When publishes
  start failing with 401, refresh it in `.env` and `restart app`. (A refresh-token
  flow is the proper long-term fix.)
- **Ollama on ARM** is CPU-only here. 24 GB RAM is plenty for `llama3.2:3b`;
  generation is a bit slower than a GPU but fine for 3 posts/day.
- **Secrets** live only in `.env` on the VM. Keep `.env` out of git (already
  ignored).
