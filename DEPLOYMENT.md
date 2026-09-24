# Boom — Deployment Guide

This document describes how to deploy Boom for production use with the **frontend on Cloudflare Pages** and the **backend on an Oracle Cloud VM** with Caddy reverse proxy (automatic HTTPS).

## Overview

Boom is a split-hosting deployment:
- **Frontend**: Deployed to **Cloudflare Pages** (React/Vite static hosting)
- **Backend**: Deployed to **Oracle Cloud VM** (FastAPI + uvicorn) with persistent disk
- **Reverse Proxy**: Caddy (automatic HTTPS via Let's Encrypt)
- **Object Storage**: Local disk on the VM (no external object storage)
- **Vector Database**: ChromaDB on the VM's persistent disk

---

## Architecture Diagram

```
┌─────────────────┐     HTTPS (Cloudflare)     ┌──────────────────┐
│  Cloudflare     │ ◄─────────────────────────► │  Oracle Cloud VM │
│  Pages (CDN)    │                             │                  │
└─────────────────┘                             │  ┌────────────┐  │
       ▲                                        │  │  Caddy     │  │
       │ HTTPS (proxied)                        │  │  :443 →    │  │
       │                                        │  │  :8000     │  │
       │                                        │  │  (uvicorn) │  │
       │                                        │  └────────────┘  │
       │                                        │  ┌────────────┐  │
       │                                        │  │  ChromaDB  │  │
       │                                        │  │  (disk)    │  │
       │                                        │  └────────────┘  │
       │                                        └──────────────────┘
       │
┌──────┴──────┐
│  Cloudflare │
│  DNS (A)    │
└─────────────┘
```

---

## Prerequisites

### Accounts Needed
1. **Cloudflare Account** — For Pages hosting and DNS
2. **Oracle Cloud Account** — For the VM (Always Free tier eligible)
3. **GitHub Account** — For GitHub → Cloudflare Pages CI/CD

### Required Local Tools
- `git`, `ssh`, `curl`
- Oracle Cloud CLI (`oci`) optional but helpful
- Python 3.11+ on the VM

---

## STEP 0 — Prepare the Repository

The repository already contains:
- `backend/` — FastAPI application (Python 3.11+)
- `frontend/` — React + Vite application
- `deploy/` — Deployment configs (systemd + Caddy)
- `DEPLOYMENT.md` — This guide

**Required files already in repo:**
```
backend/
  app/
  requirements.txt
  .env.example
frontend/
  vercel.json (removed — not needed for Cloudflare Pages)
  vite.config.ts (configured for VITE_API_URL)
  .env (VITE_API_URL= for dev)
deploy/
  boom-backend.service   # systemd unit
  Caddyfile              # Caddy reverse proxy config
DEPLOYMENT.md            # This file
```

---

## STEP 1 — Oracle Cloud VM Setup

### 1.1 Create the VM (Always Free Tier)
1. Log into [Oracle Cloud Console](https://cloud.oracle.com)
2. Create a **Compute Instance**:
   - **Shape**: VM.Standard.A1.Flex (ARM) — 4 OCPUs, 24 GB RAM (Always Free)
   - **Image**: Canonical Ubuntu 22.04 Minimal
   - **SSH Key**: Upload your public key
   - **Network**: Create new VCN with public subnet
   - **Public IP**: Assign (ephemeral or reserved)

### 1.2 Configure Security Lists / Network Security Groups
Open these ports **ingress** on the VCN:
| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22   | TCP      | 0.0.0.0/0 | SSH |
| 80   | TCP      | 0.0.0.0/0 | HTTP (Caddy ACME challenge) |
| 443  | TCP      | 0.0.0.0/0 | HTTPS (Caddy serves app) |

### 1.3 Attach Block Volume (Persistent Disk)
1. Create a **Block Volume** (50 GB free tier):
   - Size: 50 GB (adjust as needed)
   - Performance: Balanced
2. Attach to the instance (paravirtualized)
3. On the VM, format and mount:
```bash
# On the VM
sudo mkfs.ext4 /dev/oracleoci/oraclevdb
sudo mkdir -p /data
sudo mount /dev/oracleoci/oraclevdb /data
echo '/dev/oracleoci/oraclevdb /data ext4 defaults 0 2' | sudo tee -a /etc/fstab
sudo chown -R ubuntu:ubuntu /data
```
> **Note**: The mount point **must be `/data`** — the backend expects `CHROMA_DIR=data/chroma_db`, `UPLOAD_DIR=data/uploads`, `IMAGES_DIR=data/page_images` all under `/data`.
> If you actually mount the block volume at `/data`, either symlink it
> (`ln -s /data ~/boom/backend/data`) or set the `*_DIR` vars to absolute
> `/data/…` paths. The systemd unit's `WorkingDirectory` is
> `/home/ubuntu/boom/backend`, so **relative** `*_DIR` values resolve to
> `~/boom/backend/data/`, **not** `/data`.

### 1.4 Install System Dependencies
```bash
sudo apt update && sudo apt install -y \
  python3.11 python3.11-venv python3.11-dev \
  nginx curl git build-essential \
  ollama  # for local embeddings (optional, can use remote)

# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/debian/ubuntu any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# Verify
caddy version
```

### 1.5 Install Python Dependencies
```bash
# As the ubuntu user (not root)
cd /home/ubuntu
git clone <your-repo-url> boom
cd boom/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Pull Ollama model for embeddings (run once)
ollama pull nomic-embed-text
ollama serve &  # run in background or as systemd service
```

---

## STEP 2 — Backend Configuration (`.env`)

Copy `backend/.env.example` to `backend/.env` and fill in:

```bash
# LLM Configuration
LLM_PROVIDER=groq
LLM_API_KEY=your_groq_api_key_here
LLM_MODEL_NAME=llama-3.1-8b-instant
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=800

# Embeddings — local Ollama (no API key needed)
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL_NAME=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434
EMBEDDING_DEVICE=cpu

# Storage paths — relative to the systemd unit's WorkingDirectory
# (/home/ubuntu/boom/backend), i.e. these resolve to ~/boom/backend/data/…
CHROMA_DIR=data/chroma_db
UPLOAD_DIR=data/uploads
IMAGES_DIR=data/page_images

# CORS — allow Cloudflare Pages domains
CORS_ORIGINS=https://your-project.pages.dev,https://your-custom-domain.com

# App
APP_NAME=Boom AI Konkoor Mentor
APP_ENV=production
SECRET_KEY=generate-with-openssl-rand-base64-32
```

> **Note**: No R2 variables needed — all storage is local disk.

---

## STEP 2.5 — Reference Data: Book Library, Vector Store & OCR Corpus

The planning AI grounds its test blocks in the **real books** on the server —
that's why a locally generated plan names concrete sources like
«۲۰ تست حرکت‌شناسی از فیزیک ۱ خیلی سبز، صفحه ۱۵۴ تا ۱۶۲» while a bare server
only manages generic titles like «۱۶ تست از منابع کنکور».

`backend/data/` is **not in git** (see `.gitignore`) — it must be transferred
to the VM once, before the first backend start (startup auto-ingests whatever
it finds). All paths assume the repo lives at `/home/ubuntu/boom`; relative
paths in `.env` resolve against the systemd unit's `WorkingDirectory`, i.e.
`~/boom/backend/data/`.

Run these **from your laptop**, inside the repo:

```bash
ssh ubuntu@<VM> "mkdir -p ~/boom/backend/data"

# 1. Raw book PDFs — the on-disk catalog the planner names as sources.
#    Layout: data/raw/<category>/<grade>/<subject>/<Book Name>.pdf with
#    category one of: test-books, ministerial-books, custom-sources, plans
rsync -avP backend/data/raw/ ubuntu@<VM>:~/boom/backend/data/raw/

# 2. Chroma vector store (precomputed page-image + OCR-text embeddings).
#    Copying it skips a multi-hour re-embed on the free-tier CPU.
rsync -avP backend/data/chroma_db/ ubuntu@<VM>:~/boom/backend/data/chroma_db/

# 3. OCR text corpus + rendered page images (vision path + pending OCR).
rsync -avP backend/data/ocr/ ubuntu@<VM>:~/boom/backend/data/ocr/
rsync -avP backend/data/page_images/ ubuntu@<VM>:~/boom/backend/data/page_images/
```

On a slow connection, items 2+3 are the big ones — shipping just `raw/`
also works, but the VM then re-renders and re-embeds every book on first
startup (hours on the Always-Free CPU, and bulk OCR is capped per day by
`GEMINI_OCR_DAILY_CAP`).

**Verify** after the backend has started once:

```bash
ssh ubuntu@<VM> 'cd ~/boom/backend && .venv/bin/python -m app.rag.store_status'
```

- `Raw PDFs available:` must list your books — this feeds the planner's
  «منابع موجود در سامانه» catalog; empty means generic titles again.
- The **IMAGE store** should show all raw books embedded as page images;
  the **TEXT store** fills in as OCR completes (`python -m app.rag.ocr_corpus`).

**No books anywhere?** The planner still works, but falls back to
`_default_week_plan()` with titles like «۲۰ تست از منابع کنکور» — that
generic output is the symptom; this missing data is the cause.

---

## STEP 3 — Caddy Reverse Proxy

Create `/etc/caddy/Caddyfile` (or use the one in `deploy/Caddyfile`):

```caddyfile
# Replace with your actual domain
api.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
    header {
        # Security headers
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
    # Increase timeouts for long LLM requests
    timeout 300s
}
```

Install and enable Caddy:
```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl enable caddy
sudo systemctl start caddy
sudo systemctl status caddy
```

> Caddy automatically obtains and renews Let's Encrypt certificates (requires port 80 open for ACME challenge).

---

## STEP 3 — Systemd Service for Backend

Copy `deploy/boom-backend.service` to `/etc/systemd/system/`:

```ini
[Unit]
Description=Boom Backend API
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/boom/backend
Environment=PATH=/home/ubuntu/boom/backend/.venv/bin
ExecStart=/home/ubuntu/boom/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable boom-backend
sudo systemctl start boom-backend
sudo systemctl status boom-backend
journalctl -u boom-backend -f  # follow logs
```

---

## STEP 4 — Frontend Deployment (Cloudflare Pages)

### 1. Push to GitHub
```bash
git add .
git commit -m "Deploy: Cloudflare Pages + Oracle VM config"
git push origin main
```

### 2. Create Cloudflare Pages Project
1. Go to [Cloudflare Pages](https://dash.cloudflare.com/pages)
2. **Create a project** → Connect to GitHub → Select your repo
2. **Build settings**:
   - **Framework preset**: Vite
   - **Build command**: `pnpm install && pnpm run build`
   - **Build output directory**: `dist`
   - **Root directory**: `frontend`
3. **Environment variables** (in Pages settings → Environment variables):
   - `VITE_API_URL` = `https://api.yourdomain.com` (your Caddy domain)
   - `NODE_ENV` = `production`

### 3. Deploy
- Push to `main` → Cloudflare Pages auto-deploys
- Preview URL: `https://<project>.pages.dev`
- Custom domain: Add in Pages → Custom domains → `app.yourdomain.com`

### 4. Verify Vite Config
`frontend/vite.config.ts` already configured:
```typescript
proxy: {
  '/api': {
    target: process.env.VITE_API_URL || 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
},
```
In production (Vercel/Cloudflare Pages), `VITE_API_URL` is set → frontend calls `https://api.yourdomain.com/api/...` directly.
In dev (`pnpm dev`), `VITE_API_URL` is empty → Vite proxies `/api` to `http://127.0.0.1:8000`.

---

## STEP 5 — Cloudflare DNS & SSL

1. **Add DNS Records** (in Cloudflare DNS tab):
   | Type | Name | Target | Proxy |
   |------|------|--------|-------|
   | A    | @    | <VM public IP> | Proxied |
   | A    | api  | <VM public IP> | Proxied |
   | CNAME | app  | <project>.pages.dev | Proxied |

2. **SSL/TLS Settings** (Cloudflare SSL/TLS tab):
   - **SSL/TLS encryption mode**: `Full (strict)`
   - **Always Use HTTPS**: On
   - **Automatic HTTPS Rewrites**: On

---

## STEP 6 — Verify End-to-End

```bash
# 1. Backend health
curl -s https://api.yourdomain.com/health
# {"status":"ok"}

# 2. Chat endpoint
curl -X POST https://api.yourdomain.com/api/boom/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello", "history": [], "student": {}, "schedule": {}}'

# 3. Frontend loads
curl -s https://app.yourdomain.com | grep -c "Boom"

# 3. Schedule modification test
curl -X POST https://api.yourdomain.com/api/boom/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Move my math test to Friday 6 PM", "history": [], "student": {}, "schedule": {"blocks":[{"day":4,"startHour":6,"duration":2,"title":"Math Test","type":"test"}]}}'
# Should return plan_update with modified blocks
```

---

## STEP 7 — Maintenance & Operations

### View Logs
```bash
# Backend
journalctl -u boom-backend -f

# Caddy
journalctl -u caddy -f

# Ollama
journalctl -u ollama -f
```

### Update Application
```bash
cd /home/ubuntu/boom
git pull
cd backend && source .venv/bin/activate && pip install -r requirements.txt
cd ../frontend && pnpm install && pnpm run build
sudo systemctl restart boom-backend
# Cloudflare Pages auto-deploys on git push
```

### Backup ChromaDB
```bash
# Schedule via cron (daily at 3 AM)
0 3 * * * tar -czf /backup/chroma-$(date +\%F).tar.gz -C /data chroma_db
```

### Mock pool worker

Pre-generated Konkur mocks (`generated_mocks.status = 'pending_use'`) are
what lets `/api/mocks/generate` serve users instantly. The stock is
maintained by `backend/scripts/mock_pool_worker.py` (default target: 5
booklets per major × difficulty, each answer-verified before insertion).

**Windows / dev:** `start-mock-pool.bat` (repo root) opens the worker in
continuous mode; `run_boom.bat` already starts it alongside the site.

**Oracle VM:** do NOT run the continuous loop as a service - it would idle
between sweeps and compete with the backend for LLM quota. Prefer one
`--once` sweep per hour from a systemd timer or cron; each sweep tops up
only what is missing and exits:

```bash
# cron example: hourly top-up sweep (off-peak-ish, after the 3 AM backup)
0 4 * * * cd /opt/boom/backend && .venv/bin/python scripts/mock_pool_worker.py --once >> /var/log/boom-pool.log 2>&1

# or a systemd timer (OnCalendar=hourly) running:
#   /opt/boom/backend/.venv/bin/python /opt/boom/backend/scripts/mock_pool_worker.py --once
```

Useful flags:

```bash
--target 5               # pending rows kept per (major, difficulty)
--majors riazi,tajrobi   # restrict to specific majors
--difficulties konkur    # restrict difficulties (easy|konkur|hard)
--dry-run                # print deficits without generating
--interval 60            # (continuous mode only) seconds between sweeps
```

One sweep makes one LLM call per subject plus one verification call per
question, so a full top-up after a dry spell can take a while - the cron
frequency matters more than the target size. Watch `boom-backend`'s logs or
`SELECT major, difficulty, COUNT(*) FROM generated_mocks WHERE status='pending_use' GROUP BY 1,2;`
to confirm shelves stay stocked.

### Disk Space
```bash
df -h /data
# Clean old logs
journalctl --vacuum-time=7d
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `KeyError: '_type'` in ChromaDB | ChromaDB version mismatch / telemetry | `CHROMA_TELEMETRY=false` in env / restart |
| `ModuleNotFoundError: boto3` | R2 code still referenced | Ensure `storage.py` is local-only (no boto3) |
| `[Test response - real LLM not connected]` | LLM not configured | Check `LLM_API_KEY`, `LLM_PROVIDER=groq` |
| `Ollama embedding failed: 503` | Ollama not running | `ollama serve` / `systemctl start ollama` |
| CORS error in browser | Wrong `CORS_ORIGINS` | Match exact frontend domain(s) |
| Schedule changes not visible | Frontend ignores `plan_update` | Ensure `Chat.tsx` handles `data.plan_update` |
| `KeyError: '_type'` in Chroma | Old DB schema | Delete `/data/chroma_db` and re-ingest |
| Plan blocks say «تست از منابع کنکور» instead of real book/page | `backend/data/` (raw PDFs / chroma store) never copied to the VM | Transfer `backend/data/raw/` + `chroma_db/` (STEP 2.5), restart backend |
| Caddy cert not issued | Port 80 blocked | Open port 80 in Oracle security list |

---

## Cost Estimate (Monthly)

| Component | Cost |
|-----------|------|
| Oracle VM (4 OCPU, 24 GB) | Free (Always Free tier) |
| Block Volume (50 GB) | Free (first 200 GB) |
| Cloudflare Pages | Free (unlimited) |
| Cloudflare R2 | Not used (local disk) |
| Groq API | ~$0.50/1M tokens |
| **Total** | **~$0-5/mo** |

---

## Quick Start Checklist

- [ ] Oracle VM created, SSH works
- [ ] Block volume attached & mounted at `/data`
- [ ] Caddy installed, `Caddyfile` in place, ports 80/443 open
- [ ] `boom-backend.service` running, logs clean
- [ ] Ollama running (`ollama serve`), `nomic-embed-text` pulled
- [ ] `.env` configured on backend (Groq key, CORS origins)
- [ ] `backend/data/raw/` + `chroma_db/` transferred to the VM (STEP 2.5)
- [ ] `python -m app.rag.store_status` lists all books & image-embedded pages
- [ ] Frontend deployed to Cloudflare Pages, `VITE_API_URL` set
- [ ] Cloudflare DNS: A records for `api` and `app`, proxied
- [ ] SSL: Full (strict), Always Use HTTPS on
- [ ] Test: `/health`, `/api/boom/chat`, schedule modify works

---

*Last updated: September 2026*  
*Boom — Deployable AI Study Planner*