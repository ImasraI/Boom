<div align="center">
  <img src="frontend/public/logo.png" width="96" alt="Boom logo">
  <h1>Boom <span dir="rtl">بوم</span></h1>
  <p><b>AI-powered کنکور study planner</b> — smart weekly plans, cited RAG tutoring, and a ranked duel arena, in fluent Persian.</p>
  <p>
    <a href="https://github.com/ImasraI/Boom/actions/workflows/ci.yml"><img src="https://github.com/ImasraI/Boom/actions/workflows/ci.yml/badge.svg" alt="Boom checks"></a>
    <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19">
    <img src="https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
    <img src="https://img.shields.io/badge/Tailwind%20CSS-06B6D4?logo=tailwindcss&logoColor=white" alt="Tailwind CSS">
    <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  </p>
</div>

---

## What is Boom?

Boom is a full-stack study companion for Iranian کنکور candidates. It combines a **personalized planner**, an **AI tutor that cites its sources**, and a **competitive duel arena** — everything wrapped in a Persian, right-to-left interface that works on phones and desktops.

The app is organized around **three main panels** (bottom tab bar on phones, grouped sidebar on desktop):

| Panel | What's inside |
|---|---|
| 🏟️ **مسابقه (Ranked)** | Ranked duels with Elo, smart-test practice (آزمون هوشمند), leaderboard (جدول امتیازات) |
| 📅 **برنامه (Plan)** | Weekly plan (برنامه هفتگی), day-to-day plan, knowledge graph (نقشه یادگیری), exam results (آزمون‌ها) |
| 👤 **پروفایل (Profile)** | Profile, streak, evaluation (ارزیابی), recovery check-ins (ریکاوری), admin (مدیریت) |

## Highlights

- **💬 بوم AI** — chat with a tutor that answers from your own curriculum: retrieval-augmented generation over the indexed books, with `[منبع N]` citations in every answer.
- **📅 Adaptive weekly planner** — builds a realistic study schedule from your major, grade, free hours and weak subjects; replans itself as you report actual progress.
- **🧠 Knowledge graph** — the three-year curriculum as a navigable prerequisite graph, split into دروس تخصصی and دروس عمومی tabs, colored by your real accuracy.
- **⚔️ Arena** — real-time ranked duels (Elo ranks from تازه‌کار to اسطوره) with shared knowledge matching, **scheduled duels** for offline opponents (offer a time, an opponent reserves it, it starts for both), plus a daily duel quota.
- **📝 Smart tests (آزمون هوشمند)** — generated booklets with real timing, Konkoor-style negative marking, and result analysis; upload PDF/photo results for automatic grading.
- **🔥 Gamification** — streaks, XP, daily progress, recovery check-ins (sleep/mood/energy) and a weakness map built from every wrong answer you've ever made.
- **📱 Three-panel UI** — flat, GitHub-style panels with sub-tab navigation; works on phones (5-tab bottom bar) and desktop (grouped sidebar); dark mode by default.
- **🔒 Multi-user backend** — JWT auth + SMS login, per-user AI quotas and rate limits, cross-device profile/progress sync, admin panel.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · KaTeX · Recharts |
| Backend | FastAPI · Pydantic 2 · SQLAlchemy-style auth layer · Uvicorn |
| AI / RAG | ChromaDB vector store · langchain-community · hybrid retrieval · provider abstraction for **Groq / Gemini / Cerebras / Ollama / mock** |
| Data | SQLite (app data) + Chroma (embeddings), both volume-mounted in production |
| Tests & CI | `pytest` (300 tests) · `node --test` (frontend) · GitHub Actions on every push |

```
Browser ──▶ Vite dev server (:8443) ──/api──▶ FastAPI (:8000)
                                                   │
                                     ┌─────────────┼─────────────┐
                                     ▼             ▼             ▼
                                   SQLite       ChromaDB     LLM providers
                                 (users,      (curriculum    (Groq/Gemini/
                                 attempts)     embeddings)    Cerebras)
```

## Getting started

### Prerequisites

- **Python 3.12** · **Node 22** (or `pnpm` via corepack) · an LLM API key (Groq's free tier works)

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then set SECRET_KEY + LLM_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install                        # or: pnpm install
npm run dev                        # → http://localhost:8443
```

The dev server proxies `/api` to `http://127.0.0.1:8000` (override with `VITE_API_URL`), so no CORS setup is needed locally.

> 💡 Set `DISABLE_AUTH=true` in `backend/.env` for local development to skip the SMS login code (see [backend/.env.example](backend/.env.example)).

## Configuration

All backend configuration lives in [`backend/.env.example`](backend/.env.example) — copy it and fill in:

| Key | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing secret — **must** be set for production |
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL_NAME` | Chat & planner model (Groq, Gemini, Cerebras, Ollama, mock) |
| `EMBEDDING_PROVIDER` / `EMBEDDING_API_KEY` | Vector embeddings for retrieval |
| `POOL_LLM_*` / `VISION_LLM_*` | Separate providers for question-bank generation & page OCR |
| `CORS_ORIGINS` | Allowed origins in production |

## Tests

```bash
# Backend — 300 tests, mirrors CI:
cd backend
python -m pytest ../tests -q

# Frontend — unit tests + typecheck + production build:
cd frontend
npm test
npx tsc --noEmit
npm run build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs both suites on every push and pull request.

## Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for server setup, database/vector-store volume transfer, and the production checklist. In short: build the frontend (`npm run build` → `frontend/dist/`), serve it behind your web server, run FastAPI under uvicorn behind a reverse proxy, and keep `backend/data/` (SQLite + Chroma) on a persistent volume — it is git-ignored by design.

## Project structure

```
Boom/
├── backend/
│   ├── app/
│   │   ├── routers/        # auth, arena, boom_ai, schedule, admin, …
│   │   ├── rag/            # ingest, retrieval, knowledge graph, LLM providers
│   │   ├── planner/        # adaptive weekly planning engine
│   │   └── auth/           # JWT, quotas, rate limits
│   ├── data/               # runtime data (SQLite, Chroma, PDFs) — not in git
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/          # Home, Arena, Chat, Schedule, KnowledgeGraph, …
│   │   ├── components/     # PanelTabs, WeaknessMap, Experience, ui
│   │   └── navConfig.ts    # the 3-panel navigation definition
│   └── public/fonts/       # Vazirmatn (self-hosted)
├── tests/                  # 300+ backend tests
├── docs/                   # design notes, audits, screenshots
└── .github/workflows/ci.yml
```

## Docs

- [DEPLOYMENT.md](DEPLOYMENT.md) — production server setup
- [backend/README.md](backend/README.md) — RAG pipeline internals & environment deep-dive
- [docs/growth-readiness.md](docs/growth-readiness.md) · [docs/debug-audit-2026-09-27.md](docs/debug-audit-2026-09-27.md) — audits and roadmap notes

---

<div align="center"><sub>Built for students, in Persian. بوم — برنامه ریز کنکور</sub></div>
