# Boom deployment — boomedu.ir

Frontend: Cloudflare Pages. Backend: Oracle Ubuntu ARM VM, `/home/ubuntu/Boom/backend`, served by Caddy at `https://api.boomedu.ir`.

## Current audit (3 October 2026)

Read-only SSH inspection found:

| Check | Result |
| --- | --- |
| Public frontend / API health / CORS from boomedu.ir | Passed: 200 / 200 / allowed |
| Backend service / Python / dependencies | Running, Python 3.12.3; existing pip check passed |
| SQLite | Quick integrity check passed |
| Persistent JWT secret | Present, 64 characters; value was never printed |
| Deployed revision | `f3500c9`, 25 September; newer calendar endpoints return 404 |
| SMS.ir authentication | Current VM `.env` key rejected: HTTP 401, provider status 10; credit and delivery-report reads both failed |
| Query embedding service | Ollama not listening on localhost:11434 |
| Text vectors | `documents` and `question_bank`: 1024 dimensions; 18,177 total indexed rows across collections |
| Page images | None uploaded (no PNG/JPG/WebP files under backend/data) |
| Catalogue / structured OCR | Book catalogue empty; 1,547 OCR text files present, only six JSON files across data |
| Mock provider isolation | No separate pool provider/key set; currently shares chat quota |
| Production flags | APP_ENV=production, SMS_DEBUG_ECHO=false, but DISABLE_AUTH=True; change to false for an unambiguous production configuration |

The website responding does not establish that cited retrieval, OTP login or figure-based mocks work. Those checks remain blocked by the SMS credential, stopped embedding service and missing page images. Raw books are **not** required on the VM.

## Frontend release

Cloudflare Pages settings:

- Git project root: `frontend`
- Build command: `npm ci && npm run build`
- Output: `dist`
- Node: `.node-version` pins 22.16.0
- Production build variable: `VITE_API_URL=https://api.boomedu.ir` (public URL, no `/api` suffix)
- Custom domain: `boomedu.ir`; add other domains to backend CORS only if they are actually used.

The repository includes `_headers` for asset caching and browser headers. Pages handles SPA fallback without a top-level 404 page. The Vite dev proxy does not run on Pages. Cloudflare builds refuse a missing API origin; production API overrides must be HTTPS origins. Do not place API keys in `VITE_*` variables.

Official references: [Pages build environment](https://developers.cloudflare.com/pages/configuration/build-image/) and [serving pages / SPA fallback](https://developers.cloudflare.com/pages/configuration/serving-pages/).

## Backend release

Before pulling, take a consistent SQLite backup using `sqlite3.Connection.backup()` (do not copy a live SQLite database without its WAL state), and snapshot the Chroma directory while ingestion and API writes are stopped. Keep `.env` and backups private. Do not overwrite the VM's `rag_data.db` with a laptop copy: it holds live accounts, progress and plans.

After reviewing and committing the local changes, push the application branch. On the VM, pull the same revision with `git pull --ff-only` in `/home/ubuntu/Boom`. Install dependencies from the **backend** directory:

```bash
cd /home/ubuntu/Boom/backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python scripts/check_deployment.py --network --probe-embedding
```

Resolve each FAIL before release. This script is read-only: it does not send SMS, generate mocks, migrate the application database or modify vectors. It checks settings, database integrity, corpus presence, public routing/CORS, provider authentication and query-vector dimensions. A passing preflight still needs an actual login/retrieval/planning/mock smoke test.

Install the reviewed unit from `deploy/boom-backend.service`, then `sudo systemctl daemon-reload` and `sudo systemctl restart boom-backend`. Keep **one Uvicorn worker**, because arena matchmaking and rate-limit state are process-local. Caddy should proxy to `127.0.0.1:8000`; do not expose that port publicly. The unit uses the actual case-sensitive VM path `Boom`, not `boom`. Run from backend so `.env` and image paths resolve correctly.

Schema additions are applied by `ensure_schema()` on API startup. Verify `/api/health` publicly and `/api/profile/calendar` with an authenticated test account after restart; the latter should no longer return 404.

Keep one pool worker: either `POOL_WORKER_INPROCESS=true`, or a dedicated worker with this flag false. A separate `POOL_LLM_PROVIDER` / `POOL_LLM_API_KEY` prevents mock generation from exhausting chat quotas. Failed providers must remain failures, never fake booklets.

## Processing on the PC and syncing results

Scan, OCR and index on the PC. Upload only the processed corpus and referenced images; preserving relative paths matters:

- `data/chroma_db/` — complete consistent Chroma snapshot, including HNSW binaries and metadata, using the same Chroma version on both machines.
- `data/ocr/<book>/pages/page_*.json` — promoted structured question OCR, containing printed question numbers, lesson titles and options. Plain `.txt` OCR alone cannot establish verified test-number ranges.
- `data/page_images/`, `data/<student-id>/<document>/`, and cached `data/page_images/qbank/<book>/page_0001.png` — whichever locations the stored metadata references. A Chroma snapshot does not include the referenced images.
- Optional catalogue metadata can be imported through the existing catalogue tools; it does not require copying the user database.

Do not replace the live application database. Do not copy a Chroma SQLite file by itself while indexing is running. Stop writes on both ends when making/replacing the snapshot, and keep a backup of the VM corpus. Maintain user IDs: shared corpus ownership must match `DEMO_USER_ID`; don't silently expose another student's private uploads.

Query-time embeddings are still required on the VM. Their **model**, preprocessing and dimension must match the PC indexing model. A different model with the same dimension is also incompatible. The legacy PC `.env` specified `aligh4699/heydariAI-persian-embeddings`, while the VM specified `nomic-embed-text`; neither name was stored in the old collection metadata, so these settings do not prove indexing provenance. The Gemini migration below resolves this by re-embedding the stored text in new collections with a known model and retrieval format. Do not delete old vectors or pad/truncate them to conceal a mismatch.

Ollama specifically is optional: a compatible local Python model or reachable embedding API can serve query embeddings. With the current Ollama configuration and no running service, the app falls back to lexical/BM25 retrieval when query vectors are empty; it does not perform semantic search against the stored text vectors. Processing books offline removes ingestion work from the VM, not the need to represent each new question in the same vector space.

Record the model name/version and collection dimensions alongside each future corpus snapshot.

## Gemini text embeddings (new setup)

Boom supports Google's hosted `gemini-embedding-2` with 768 dimensions. It
requires no Ollama process on the VM. Both document indexing and live search
must use the same model, dimensions and retrieval prompt version. The Gemini
adapter uses the synchronous embedding endpoint, not the paid asynchronous
Batch API. Free-tier availability and actual quotas depend on your Google
project and supported region; check Google AI Studio before deployment.

Run the migration on the laptop from `backend/`:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/migrate_gemini_embeddings.py --activate
```

Linux equivalent: `.venv/bin/python scripts/migrate_gemini_embeddings.py --activate`.
To use the laptop OCR worker credentials with three parallel embedding workers:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/migrate_gemini_embeddings.py --workers 3 --activate
```

Keys are read only from the ignored `ocr-workers/worker1..3/worker.env` files.
Each distinct key is probed first; refused credentials are reported. If fewer
working credentials remain, all three workers use those working credentials,
with explicit source assignments in the status file. Duplicate credentials
share one rate limiter and quota cooldown. Three workers do not imply three
independent quotas: Google applies quotas per project, not per API key. Worker
threads call the embedding API; one coordinator writes Chroma and validates the
finished collections, preventing concurrent index writers and duplicate chunks.

`--probe-only` checks the key and query vector without starting a rebuild.
For faster ingestion with automatic response to actual per-minute quota errors:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/migrate_gemini_embeddings.py --workers 3 --auto-rate --rpm 100 --batch-size 8 --activate
```

The supplied RPM is an initial ceiling, not a claim about Google's quota. All
workers sharing a key share the adaptive rate and cooldown. Actual quota metrics
and retry delays are recorded without credentials or document text. Daily quota
errors still stop immediately; a larger token-per-minute allowance cannot bypass
the project's per-day embedding request limit.

`--rpm` and `--batch-size` control ingestion throughput (migration defaults to
at most 5 requests/minute with 8 chunks/request to reduce token spikes). A stopped run can be
resumed with the same command: successfully stored, unchanged chunks are skipped.
It re-embeds text already stored in Chroma, preserving IDs, user ownership,
book/page citations and printed question numbers. Raw PDFs are unnecessary.
After validation, activation writes the working worker key to `EMBEDDING_API_KEY`
and its proxy to `EMBEDDING_PROXY`; the chat and vision credentials are preserved.
The localhost laptop proxy must not be copied to the VM unless that same proxy
actually runs there.

Old `documents` and `question_bank` collections remain intact. New collections
are `documents_gemini-embedding-2_768_retrieval_v1` and
`question_bank_gemini-embedding-2_768_retrieval_v1`. The application automatically
selects these names for Gemini; keep the configured base names unchanged.
Image collections keep their existing backend and are not rebuilt by this text
migration. Do not configure CLIP queries against Gemini text vectors.

Progress is saved in `backend/data/embedding_migrations/gemini-status.json`.
For a live overall count and worker health check, run from `backend/`:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/embedding_status.py --watch
```

The viewer reports remaining chunks across both collections, identifies an
exited worker even if its last saved status was `running`, and shows whether
Gemini is being contacted or a quota/retry delay is in progress. Ctrl+C closes
only the viewer. The migration stores its actual Python worker PID and rejects
duplicate migration jobs with an operating-system lock.

Only a complete, validated migration with `--activate` switches the laptop's
`backend/.env`; its previous configuration is backed up in the ignored migration
directory. Restart the backend afterward because its vector/lexical stores are
cached. If quota or connection errors interrupt indexing, the original setup
remains active. Query-time provider errors fall back to lexical retrieval.

After a successful rebuild, export and import the verified shared text bundle
as described below, preserving the VM's existing corpus and live user database.
Upload referenced processed images separately. Set the VM's `backend/.env`:

```dotenv
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL_NAME=gemini-embedding-2
EMBEDDING_DIMENSIONS=768
EMBEDDING_BATCH_SIZE=24
EMBEDDING_REQUESTS_PER_MINUTE=10
EMBEDDING_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
EMBEDDING_API_KEY=<your verified private project key>
EMBEDDING_PROXY=
```

`EMBEDDING_API_KEY`, if set, overrides `GEMINI_API_KEY`; clear any old
non-Gemini embedding key. Restart the backend and run
`scripts/check_deployment.py --probe-embedding`. Changing `.env` alone does not
convert old vectors. The migration program and provider code belong in Git;
vectors, keys, OCR, page scans, model caches, logs and progress files do not.

### Preserve the VM corpus when uploading new text vectors

After migration completes and activates, export just the shared Gemini text
collections from the laptop, with ingestion stopped:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/transfer_shared_corpus.py export --file data/embedding_migrations/shared-gemini.json
```

This validates the source migration and exports only records owned by
`DEMO_USER_ID`. Transfer the ignored JSON file over SSH. On the VM, back up
the Chroma directory, stop backend/ingestion writers and run from backend:

```bash
.venv/bin/python scripts/transfer_shared_corpus.py import --file data/embedding_migrations/shared-gemini.json
```

The importer validates the checksum, embedding provenance, dimensions, document
and citation digests and account ownership before any writes. It preserves
existing collections and refuses IDs that collide with private documents.
Interrupted imports can be repeated; imported batches are verified immediately.
The application database is never opened. Do not activate the VM Gemini settings
until import verification passes. Existing private documents in legacy embedding
collections also need migration to become available in the new semantic index.
This file does not include page images, structured OCR or catalogue entries;
upload those processed resources separately to retain verified book ranges and
figure-based retrieval.

Google's free-tier inputs may be used to improve its products. Keep keys in
`backend/.env`, never frontend environment variables. See the official
[embedding guide](https://ai.google.dev/gemini-api/docs/embeddings),
[pricing](https://ai.google.dev/gemini-api/docs/pricing), and
[project rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

## SMS.ir OTP diagnosis

The app calls `/v1/send/verify` immediately, with no scheduled send time. Configure:

```dotenv
APP_ENV=production
DISABLE_AUTH=false
SMS_DEBUG_ECHO=false
SIGNUP_BYPASS_CODE=
SMS_BASE_URL=https://api.sms.ir
SMS_API_KEY=<valid private API key from the current SMS.ir panel>
SMS_VERIFY_TEMPLATE_ID=916577
SMS_VERIFY_PARAMETER_NAME=OTP
SMS_TRUST_ENV=false
SMS_PROXY=
```

`OTP` is the default; replace it with the exact case-sensitive placeholder in approved template 916577 if different. The current key must be repaired first; HTTP 401 is an authentication failure, not evidence of nighttime queuing. Reload the backend after changing credentials.

New logs contain `message_id`, UTC acceptance timestamp and template ID, never the OTP or mobile number. Enter that ID in the admin panel's delivery lookup (or use the admin-only `/api/admin/sms-delivery/{id}` endpoint). It returns timestamps and provider state only; mobile numbers and message text are stripped. Its official SDK documents `SendDateTime`, `DeliveryState`, and `DeliveryDateTime`: [verification and delivery reports](https://github.com/IPeCompany/SmsPanelV2.DotNet).

For messages arriving at 08:00 the next day, compare provider acceptance and delivery timestamps. If acceptance was immediate but delivery was delayed, ask SMS.ir support to inspect the template/service route and operator queue using the message IDs. Nighttime restrictions or route classification are hypotheses until the report confirms them. If the provider itself accepted only the next morning, inspect its queue/scheduling configuration. The backend contains no 08:00 scheduler. Do not extend OTP expiry overnight; codes should remain short-lived.

## Release verification

Local validation for this revision: 379 backend tests passed, 2 skipped; 16 frontend tests passed; TypeScript and the Cloudflare production build passed; pip check passed. Local unauthenticated calendar and SMS-report reads return 401. Desktop planning/profile and mobile layouts were inspected; the knowledge graph rendered 31 nodes for the test account without document-level horizontal overflow.

The 4 October deployment imported and verified 1,783 shared document chunks and
126 question-bank chunks using Gemini embeddings at 768 dimensions, plus 18,201
processed OCR files. Existing accounts and learning records and the persistent
JWT secret were verified against the private VM backup. Cloudflare served the
new build, real logo PNG and self-hosted font files. Authenticated VM smoke checks
used an isolated application database: daily 480-minute planning, verified book
question ranges, no overlaps, manual/repeat stability, account isolation,
knowledge graph, semantic retrieval, cited chat and live mock generation passed.
The local Cerebras pool credential returned HTTP 402; the VM uses a verified
dedicated Gemini pool key instead, keeping mock generation off the Groq chat
quota. The VM reranks eight candidates on its two CPU cores. Image retrieval
skips model loading while page files are absent and detects subsequent uploads.
SMS authentication and positive credit passed, but actual OTP delivery timing
and image-based answers still require verification after an approved recipient
and page images are available.

The direct pinned-dependency audit was reduced from 69 advisory entries across eight packages to three entries for Chroma alone. These are advisory entries, not 69 distinct confirmed exploitable application bugs. Chroma's format-sensitive dependency was retained; its remaining advisories need deployment-context review. Frontend production dependencies had no reported npm audit vulnerabilities. This is not a claim that every transitive dependency or production workflow has been cleared.

Run backend pytest, frontend tests, TypeScript and a production build before pushing. After deploying, use a test account to check immediate OTP delivery, a cited chat answer with an actual page image, weekly plan hours/book ranges/no overlaps, manual repeat stability after regeneration, a generated mock, and account-switch isolation. Do not claim a release is ready based only on `/api/health`.

Backend dependency upgrades in this change need installation on the VM. Chroma remains pinned at 0.5.5 to preserve existing corpus compatibility: audit advisories for its HTTP server / remote model loading are not a reason to silently migrate the uploaded vector format. This app uses a private embedded PersistentClient. Never expose a Chroma HTTP server, enable remote model code, or ingest untrusted serialized model configurations.
