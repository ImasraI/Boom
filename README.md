# Boom — AI Konkoor Mentor + RAG

Boom's original frontend is kept, while the RAG backend from the uploaded Lapeace/university-ai-assistant project has been integrated into `backend/`.

## Architecture

- `frontend/` — existing Boom React/Vite UI
- `backend/app/rag/` — Chroma + hybrid retrieval + Groq/LLM RAG pipeline
- `backend/app/routers/boom_ai.py` — Boom chat and multi-month study-plan endpoints
- `backend/data/chroma_db/` — existing RAG vector store from the uploaded Lapeace project
- `backend/data/uploads/` — existing indexed documents/uploads

## Run backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows
# cp .env.example .env # Linux/macOS
uvicorn app.main:app --reload --port 8000
```

Make sure your Groq API key is set in the `.env` file. The default configuration expects `LLM_PROVIDER=groq` and `EMBEDDING_PROVIDER=groq` with the respective API keys.

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL. The frontend proxies `/api` to `http://localhost:8000`.

## Important prototype note

Boom's current frontend uses a local demo login, so `/api/boom/chat` and `/api/boom/study-plan` use `DEMO_USER_ID=1`. Before production, replace this with Boom's real authentication and pass the authenticated student ID into the RAG/planner layer.

## Windows one-click setup

Double-click `run_boom.bat` from the project root. It checks/installs Python 3.13, Node.js LTS, and creates the backend virtual environment, installs Python and npm dependencies, creates `.env`, starts the backend and frontend servers in separate windows.

Requirements: Windows 10/11 with `winget` available and an internet connection for the first setup. The Aya model is several GB, so the first model download can take time.


### Windows Python
The included `run_boom.bat` prefers Python 3.12. Python 3.12 is recommended for the backend dependencies; Python 3.14 is not required.
