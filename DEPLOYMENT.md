# Boom — Deployment Guide

This document describes how to deploy Boom for production use with the frontend on Vercel and the backend on Fly.io.

## Overview

Boom is a split-hosting deployment:
- **Frontend**: Deployed to Vercel (React/Vite)
- **Backend**: Deployed to Fly.io (FastAPI + uvicorn)
- **Object Storage**: Cloudflare R2 for page images (with local disk fallback)
- **Vector Database**: ChromaDB with local persistent disk on the backend host

---

## STEP 0 — Prerequisites

### Accounts Needed
1. **Cloudflare Account** — For R2 bucket creation
2. **Vercel Account** — For frontend deployment
3. **Fly.io Account** — For backend deployment

### Required Environment Variables

#### Backend (.env in backend/ directory)
```
# LLM Configuration
LLM_PROVIDER=groq
LLM_API_KEY=your_groq_api_key
EMBEDDING_PROVIDER=ollama
EMBEDDING_API_KEY=  # Leave empty for local Ollama

# Cloudflare R2 (optional - local fallback works)
R2_ACCOUNT_ID=your_r2_account_id
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_BUCKET_NAME=your_r2_bucket_name

# Application paths
CHROMA_DIR=data/chroma_db
UPLOAD_DIR=data/uploads
IMAGES_DIR=data/page_images

# CORS
CORS_ORIGINS=https://your-vercel-app.vercel.app
```

#### Frontend (.env in frontend/ directory)
```
# Vite API URL - set this in Vercel dashboard
VITE_API_URL=https://your-backend.fly.io

# Development: Leave empty to use local proxy
# VITE_API_URL=

# Development server port
PORT=8443

# Figma public URL (optional)
FIGMA_PUBLIC_URL=
```

---

## STEP 1 — Cloudflare R2 Setup

### 1. Create an R2 Bucket
1. Go to [Cloudflare R2](https://dash.cloudflare.com/r2)
2. Click "Create bucket"
3. Give it a name (e.g., `boom-images`)
4. Note the bucket name and settings

### 2. Get R2 Credentials
1. Go to [R2 API Tokens](https://dash.cloudflare.com/api-tokens)
2. Click "Create token"
3. Give it a name (e.g., `boom-r2-token`)
4. Permissions: `R2:Read Write`
5. Note these values:
   - **Account ID** (from the URL: `https://dash.cloudflare.com/ACCOUNT_ID/...`)
   - **Access Key ID**
   - **Secret Access Key**

### 3. Update Backend .env
Add the R2 credentials to `backend/.env`:
```
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=your_bucket_name
```

### 3. Verify R2 Works
Run a quick test:
```bash
cd backend
python -c "
from app.utils.storage import put_object, get_object
put_object('test/key.png', b'test data')
data = get_object('test/key.png')
print('R2 working!' if data == b'test data' else 'Local fallback working')
"
```

---

## STEP 2 — Fly.io Backend Deployment

### 1. Install Fly CLI
```bash
flyctl auth signup  # or login
flyctl auth login
```

### 2. Initialize Fly Project
```bash
cd boom-merged
flyctl init --name boom-app
```
This creates a `fly.toml` file (we already provided one).

### 2. Add Persistent Volume
```bash
flyctl volumes create data --size 1GB --region iad
```
This creates a persistent volume mounted at `/app/data`.

### 2. Set Environment Variables
```bash
flyctl secrets set \
  LLM_PROVIDER=groq \
  LLM_API_KEY=your_groq_key \
  EMBEDDING_PROVIDER=ollama \
  R2_ACCOUNT_ID=your_r2_account_id \
  R2_ACCESS_KEY_ID=your_r2_access_key \
  R2_SECRET_ACCESS_KEY=your_r2_secret_key \
  R2_BUCKET_NAME=your_r2_bucket_name \
  CORS_ORIGINS=https://your-vercel-app.vercel.app
```

### 3. Deploy
```bash
flyctl deploy
```

### 2. Verify Deployment
```bash
flyctl status
flyctl logs --tail
```

### Fly.io Notes
- **Free tier**: Always-on for small apps
- **Persistent volumes**: Additional cost (~$7/month for 1GB)
- **URL**: `https://boom-app.fly.app`

---

## STEP 3 — Vercel Frontend Deployment

### 1. Prepare Frontend Environment
1. Go to Vercel Dashboard → Your Project → Settings → Environment Variables
2. Add `VITE_API_URL`:
   - Value: `https://your-backend.fly.app` (your Fly.io app URL)
3. Optionally add `FIGMA_PUBLIC_URL` if you have a custom domain

### 2. Verify Vercel Project Settings
- Framework: Vite
- Build Command: `pnpm install && pnpm run build`
- Output Directory: `dist`
- Root Directory: `/` (root of frontend folder)

### 3. Deploy
```bash
vercel --prod
# or connect your GitHub repo for automatic deployments
```

### 4. Verify Deployment
- Visit your Vercel URL
- Test that the chatbot works
- Test schedule modification functionality

### Vercel Notes
- The `vercel.json` we created sets `VITE_API_URL` automatically via `@vercel/appDomain`
- Make sure the proxy in `vite.config.ts` works: `target: process.env.VITE_API_URL || "http://127.0.0.1:8000"`
- The frontend will proxy `/api` calls to the backend

---

## STEP 5 — Full Deployment Checklist

### Backend (Fly.io)
- [ ] Fly CLI installed and logged in
- [ ] `fly.toml` configured with correct app name
- [ ] Persistent volume attached (`flyctl volumes create data`)
- [ ] All secrets set via `flyctl secrets set`
- [ ] `flyctl deploy` successful
- [ ] Backend URL confirmed (e.g., `https://boom-app.fly.app`)
- [ ] Ollama is running on the host (or install: `ollama serve`)

### Frontend (Vercel)
- [ ] Vercel account connected to GitHub
- [ ] `VITE_API_URL` set to backend URL
- [ ] `vercel.json` in frontend root
- [ ] `vercel deploy` successful
- [ ] Frontend URL confirmed (e.g., `https://boom.vercel.app`)

### R2 (Cloudflare)
- [ ] R2 bucket created
- [ ] API tokens created
- [ ] Credentials added to Fly.io secrets
- [ ] Test `put_object`/`get_object` works

### Data & Content
- [ ] Any existing PDFs re-ingested (run `python -m app.rag.ingest_raw` if needed)
- [ ] Chroma DB data persists across Fly.io restarts (stored in volume)
- [ ] Test schedule modification works end-to-end

### Testing Checklist
- [ ] Chatbot starts and uses Groq LLM (not mock)
- [ ] Schedule modification works (add/test/change events)
- [ ] PDF content can be read (if ingested)
- [ ] Page images load via R2 or local fallback
- [ ] CORS allows frontend-backend communication
- [ ] No `[Test response - real LLM is not connected]` messages

---

## Troubleshooting

### Common Issues

1. **"[Test response - real LLM is not connected]"**
   - ❌ Ollama not running on backend host
   - ❌ `LLM_PROVIDER` not set to `groq` in `.env`
   - ❌ `LLM_API_KEY` not set or invalid

2. **"Embedding model failed: 503"**
   - ❌ Ollama not running
   - ❌ `nomic-embed-text` model not pulled: `ollama pull nomic-embed-text`
   - ❌ `EMBEDDING_PROVIDER` not set to `ollama`

3. **CORS errors**
   - ❌ `CORS_ORIGINS` not set to include Vercel URL
   - ❌ Frontend `VITE_API_URL` not set

4. **R2 errors**
   - ❌ R2 credentials incorrect
   - ❌ Bucket name wrong
   - ❌ Fallback to local disk (check logs for "Falling back to local disk")

5. **Chroma data lost after restart**
   - ❌ Persistent volume not attached in Fly.io
   - ❌ `data/` directory not mounted

6. **Schedule modifications not working**
   - ❌ No PDF content ingested (system works without PDFs, but needs content for intelligent scheduling)
   - ❌ `###UPDATE_PLAN###` marker not in LLM response
   - ❌ Schedule conflict detected (e.g., trying to add test when slot already occupied)

### Getting Help
- Check `flyctl logs --tail` for backend issues
- Check Vercel dashboard logs for frontend issues
- Check Cloudflare R2 dashboard for storage issues
- Review `backend/logs/` for application logs

---

## Additional Notes

### Why Fly.io + Fly.io Volumes?
- Fly.io's free tier is always-on (unlike Vercel's free dynos that sleep)
- Persistent volumes ensure Chroma DB and page images survive restarts
- Simple `fly.toml` configuration
- Good documentation and support

### Why Cloudflare R2?
- S3-compatible API (easy boto3 integration)
- No egress fees for downloads
- Generous free tier (10GB storage, 1GB bandwidth/month)
- Global CDN for fast image delivery

### Why Vercel for Frontend?
- Zero-config Vite deployment
- Automatic HTTPS with custom domains
- Easy environment variable management
- Great developer experience

---

## Quick Start Summary

If you want to get started immediately:

1. **Create R2 bucket** and get credentials
2. **Set up Fly.io** with persistent volume
3. **Set environment variables** on both Fly.io and Vercel
4. **Deploy backend**: `flyctl deploy`
5. **Deploy frontend**: `vercel --prod` or connect GitHub
6. **Test**: Chatbot should work, schedule modification should function

---

*Last updated: September 2026*
*Boom — Deployable AI Study Planner*