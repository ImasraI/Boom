# Boom (بوم)

<img src="frontend/public/karzar-shield-detailed.png" width="96" alt="Karzar shield">

Persian کنکور study companion with a weekly planner, a cited RAG tutor, a
curriculum graph and the کولوسئوم ranked arena. The application still uses the
Boom name; the shield is the asset for the planned کارزار rebrand.

## Product

The phone navigation and desktop sidebar share three panel groups:

| Panel | Contents |
| --- | --- |
| کولوسئوم | Ranked duels, practice mocks and leaderboard |
| برنامه | Weekly schedule, learning graph, recorded results and upcoming exams |
| پروفایل | Profile, streak, evaluation and administrator tools |

- Weekly planning uses saved availability, confirmed homework, recorded progress,
  upcoming exam topics and documented book questions. Manual and recurring
  commitments survive regeneration. Missing source ranges are disclosed.
- Chat renders Persian Markdown, tables and mathematics with source citations.
- The knowledge graph uses promoted book curriculum and prerequisites. Accuracy
  comes from attempted questions; untouched topics are not fabricated weaknesses.
- Grade-12 math/physics ranked matches have ten questions from the next reviewed
  Maze exam scope. Old or incompatible question stock is excluded, and an empty
  weekly bank returns a clear availability error instead of live placeholders.
- Full math/physics mocks use 40 mathematics, 35 physics and 30 chemistry questions.
  The four difficulty levels are easy, konkur, hard and extreme within the curriculum.
- Drafting and verification use separate durable queue stages. Source grounding,
  blind solving and quality auditing gate publication. Reported questions are
  excluded individually while valid siblings and historical attempts remain saved.
- Profiles, calendars, task progress and private exam records belong to the
  signed-in account. Backend quotas and admin permissions apply independently.

## Study desk and RAG debugging

Sunset is the default palette, with muted crimson and rose surfaces, Nazanin display
headings and Vazirmatn controls. The top settings shortcut opens Profile's
Settings tab directly. Motion respects the operating system and calm preference;
sounds are opt-in. The home rings show completed scheduled tasks, not inferred
mastery. Schedule face offsets preserve the actual time-aligned back planes.

The admin RAG console has separate visualization and stage-record views: source
shelves, documents and chunks, query embedding provenance, retrieval flow, rank
changes, actual candidate counts and final context. Sample rows, missing counts,
truncation, skipped stages and explicit answer citations are labelled separately.
Source-node coordinates describe relationships, not vector distances. Trace data
is bounded, secret-redacted, private to admins and kept only in process memory.

Local synthetic previews live in ignored `frontend/dev-previews/`; Vite's
allowlisted development middleware serves them without copying them into the
production build. `frontend/scripts/preview-rag-inspector.mjs` creates an offline
RAG layout fixture without accounts or provider requests.

## Stack and storage

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, KaTeX and Recharts |
| Backend | FastAPI, Pydantic, SQLAlchemy and Uvicorn |
| Retrieval | Chroma, lexical/semantic retrieval and optional cross-encoder reranking |
| Models | Groq, Gemini, Cerebras, Ollama and deterministic test providers |
| Persistence | `backend/rag_data.db`, `backend/data/chroma_db`, processed OCR and uploads |
| Checks | Pytest, frontend Node tests, TypeScript and production builds |

Runtime data, original PDFs, imported exam archives and credentials are excluded
from Git. Query embeddings must use the same model and dimensions as the stored
vectors; changing the environment does not migrate existing collections.

## Local development

Use Python 3.12 and Node 22. Run each server from its own directory because
backend `.env` paths resolve from its working directory.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Configure providers and a persistent SECRET_KEY in backend/.env.
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev                    # http://localhost:8443
```

Vite proxies `/api` to `http://127.0.0.1:8000`. `VITE_API_URL` sets a different API
origin. For isolated local development, `DISABLE_AUTH=true` bypasses SMS; it must
be disabled in production. Never put backend API keys in frontend settings.

See [backend/.env.example](backend/.env.example) for provider, quota, storage and
production settings. Keep the actual `backend/.env` ignored.

## Validation

```bash
cd backend
python -X utf8 -m pytest ../tests -q --no-header -p no:cacheprovider

cd ../frontend
npm test
npx tsc --noEmit -p tsconfig.json
npm run build
```

On PowerShell use `npm.cmd` and `npx.cmd`. Backend tests use temporary databases.
Passing plumbing tests does not establish scientific question quality, OCR
accuracy, production readiness or delivered SMS.

## Deployment and local corpus work

The production architecture is Cloudflare Pages for the frontend and an Oracle VM
for FastAPI. [DEPLOYMENT.md](DEPLOYMENT.md) contains setup guidance. Preserve the
VM application database, private uploads and JWT secret; back up SQLite through
its backup API and Chroma with writers stopped before a reviewed deployment.
Processed corpus/vector transfer is separate from Git. A successful health check
alone does not validate authenticated workflows or model availability.

The current exam-corpus import is **local only**. Its native extraction completed
19,233 pages from 222 unique PDFs with zero recorded failures. Only three style
questions have been visually checked, without teacher or scientific approval.
Bulk visual transcription and structured question review are not complete; see
the handoff for checkpoint status, provider pauses and safe resume commands.

## Canonical documentation

- [Exam corpus handoff](docs/EXAM_CORPUS_HANDOFF.md): import operations, scanning
  evidence, quality boundaries and commands.
- [Question authoring roadmap](docs/QUESTION_AUTHORING_ROADMAP.md): prioritized
  improvements and evaluation before training.
- [Question design schema](docs/QUESTION_DESIGN_SCHEMA.md): literal evidence,
  inferred design and separate review status.
- [Question quality](docs/question-quality.md): generation and publication gates.
- [Weekly ranked](docs/weekly-ranked.md): rolling Maze scope and event preparation.
- [Homework planning](docs/HOMEWORK_PLANNING.md): confirmed work and calendar sync.
- [Book knowledge graph](docs/BOOK_KNOWLEDGE_GRAPH.md): promoted curriculum evidence.
- [Provider failover](docs/pool-provider-failover.md): quota handling and worker roles.
- [Data model](docs/data_model.md): persistent records and ownership.
- [Growth roadmap](docs/growth-readiness.md): remaining infrastructure work.
- [Brand asset](docs/karzar-logo.md): the sole shield logo.

Operational scripts remain in `backend/scripts/`, deployment configuration in
`deploy/`, and regression tests in `tests/` and `frontend/`. Historical audit
snapshots are not current run instructions.
