# Local exam corpus: agent handoff

## Authorization and ownership

Local work only in `C:/Users/Arsam/Desktop/Boom-merged`. The user will authorize
pushing later. Do not SSH to the VM, upload/import data there or push this work.
Local commits follow the user's explicit authorization. Preserve concurrent
emoji-cleanup/RAG-inspector changes. No API keys in
prompts, source, logs, Git or frontend settings. `mocks/`, `backend/data/` and
scratch verification scripts are ignored.

Read [QUESTION_AUTHORING_ROADMAP.md](QUESTION_AUTHORING_ROADMAP.md) and
[QUESTION_DESIGN_SCHEMA.md](QUESTION_DESIGN_SCHEMA.md). Those documents distinguish implemented imports
from future authoring/validation/training improvements.

## Verified status (updated 14 October 2026)

- Eight RARs plus two direct PDFs produced 222 unique PDFs, 33 duplicate copies,
  and 19,233 pages. Originals are preserved; PDF identity is SHA-256, not filename.
- Native text/layout extraction completed for all 19,233 pages with zero recorded
  page failures. The layout refresh is complete as well, retaining explicit image
  bounds/layout-version metadata. Read `native-status.json` for stored counts.
  This does not mean visual OCR or question approval is complete.
- The pilot compared PyMuPDF, PDFium, Tesseract fas+eng, cached EasyOCR fa+en on
  the laptop GPU, Gemini native vision and Groq Qwen vision. Seven pages have
  saved local-engine outputs. Cloud results are failures/candidates, not approvals.
- Three questions on a rendered official math-physics page were visually checked
  and standardized as style references. They are marked `visual_checked`,
  `human_reviewed=false`, `scientific_state=not_checked`. This is a subset of that
  page, not a claim of whole-page coverage or teacher certification.
- A live local high-reasoning GPT-OSS-120B draft successfully used an actual
  textbook excerpt plus a qualified style reference. It is saved privately as
  `generation-trial.json`, is not a copied source stem, and remains an unpublished
  trial. The ordinary source/solver/audit gates still decide production eligibility.
- All five locally discovered Gemini credentials returned daily request quota
  limits of 20. All four Groq vision credentials hit the 1,000-output-token-per-minute
  capacity mismatch with the requested high-reasoning output. Waiting or repeated
  identical requests will
  not fix that hard capacity mismatch. Do not lower quality or turn truncated
  output into usable references.
- Saved Gemini retry-not-before is about **2026-10-14 08:00 UTC / 11:30 Tehran**.
  It was conservatively calculated before Windows timezone data was installed.
  Keep the saved deadline; do not move it earlier by clearing quota state.

## Retry on 14 October, after the saved deadline

A bounded seven-page Gemini retry was made after the saved deadline. Two bounded retries returned no new candidates. All five
credentials returned HTTP 503, so the run saved a 15-minute cooldown and stopped
with zero new vision candidates. This run does not establish that daily quotas
are exhausted: HTTP 503 is provider availability, not a daily-quota refusal.
Read the current `scan-status.json` and `vision-quota.json` before resuming; the
older quota deadline above is historical. Native extraction remains complete,
and the three qualified visual pilot references remain intact. No OCR worker is
currently alive. Groq's recorded hard request-size/capacity blocks remain.

## Implemented modules

| Module | Purpose |
| --- | --- |
| `app/rag/exam_inventory.py` | Archive member validation, content deduplication, source aliases and PDF inventory |
| `app/rag/exam_corpus.py` | Source hashes, atomic page records, native spans and coordinates, lazy render signatures, OS worker lock and safe PID liveness |
| `app/rag/exam_vision.py` | Ignored local env credentials, actual image requests, high reasoning, secret-safe failures, persistent quota/access/capacity state |
| `app/rag/exam_scanning.py` | Pilot benchmark, page-layout pass, one-question groups, partial checkpoints, schema checks, strict cross-checking and content/image-bound review |
| `app/rag/exam_style.py` | Bounded style retrieval by confirmed major, subject and current topic; source-copy check |
| `scripts/import_exam_examples.py` | Local CLI, optional saved-deadline watch and queued worker lock |

Generation adds style context **after** textbook evidence, in a separate untrusted
JSON section. It requires book context, a known single major and a matching current
topic. It cannot add curriculum topics, replace book citations, provide answers to
the blind solver or weaken existing verification. Literal source copies and the
same long stem with only numerical/variable substitutions are dropped. This is
not a complete semantic novelty detector.
`style_prompt_reference_ids` records which examples were supplied; it is not proof
that the model used every example.

The question-design schema document describes the fuller future schema. Current
`style-index.json` uses a flatter source layout with `document_id`, `pdf_page`,
`printed_page`, `question_number`, `major`, `subject`, `topic`, `literal`, `design`,
`image`, `literal_sha256`, `extraction_state`, `scientific_state`,
`human_reviewed`, `inferred_design` and `page_fully_transcribed`.

## Commands (PowerShell, from repository root)

```powershell
cd backend
.venv/Scripts/python.exe -X utf8 scripts/import_exam_examples.py status
.venv/Scripts/python.exe -X utf8 scripts/import_exam_examples.py inventory
.venv/Scripts/python.exe -X utf8 scripts/import_exam_examples.py extract
.venv/Scripts/python.exe -X utf8 scripts/import_exam_examples.py benchmark --local-only --limit 7
```

The laptop HTTP proxy on port 10809 successfully reached the providers; direct
Gemini generation connections were reset. Use only for the local scan process
when that proxy is running. This is not VM configuration:

```powershell
$env:EXAM_OCR_PROXY='http://127.0.0.1:10809'
.venv/Scripts/python.exe -X utf8 scripts/import_exam_examples.py scan --provider gemini --workers 3 --limit 7 --watch --wait-for-lock
```

Start with this bounded pilot after the saved quota deadline. `--watch` sleeps
until the saved provider retry time; it does not repeatedly probe a blocked key.
`--wait-for-lock` queues behind the current native extraction. It stops if access
or capacity requires action, or the selected scan is finished/quarantined. The
default command without `--limit` selects the full inventory; do not launch a
large unattended vision import before the pilot is visually checked. The scanner
has not earned a measured production accuracy rate.

Automatic execution review blocked attempts to launch a detached Windows worker
with `Start-Process`. No detached worker was started. The already-running native
extraction was left alone. Do not claim a future scan has been scheduled/running
unless `coordinator-status.json` and actual process liveness confirm it.

## Private checkpoint files

Under `backend/data/exam_examples/`:

- `inventory.json`: source identities, aliases and expected page counts.
- `documents/<sha>/native/page_NNNNN.json`: literal/search copies, spans and quality
  surrogate. Native extraction is never question approval.
- `documents/<sha>/images/page_NNNNN.png` plus `.render.json`: preserved page,
  source hash, DPI and engine version. Rendering is lazy; not every page is PNG yet.
- `documents/<sha>/vision/page_NNNNN/<parts>/`: layout and per-question request
  checkpoints keyed by prompt digest. A quota/network refusal cannot erase
  successful parts. A partial/uncertain transcript stays unqualified.
- `documents/<sha>/vision/page_NNNNN.<provider>.json`: assembled page candidate.
- `page_NNNNN.visual.json` and `.review.json`: corrected visual candidate and
  specific question review. Approval binds the exact data digest and image hash;
  stale reviews and blanket approval without question IDs are rejected.
- `vision-quota.json`: private per-credential/model refusal state. The application
  quota file is read for existing blocks and is not overwritten by the scanner.
- `native-status.json`, `scan-status.json`, `coordinator-status.json`: phases,
  actual progress/heartbeat, pending work and saved retry deadline.
- `benchmark-status.json`, `benchmark/`, `generation-trial.json`: private pilot
  outputs. Raw text/reasoning/API response dumps are not console logs.
- `style-index.json`: only qualified references, with scientific review separate.

## Validation and next work

The final full backend suite passed **843 tests, 3 skipped**; the frontend suite
passed **87 tests**. Strict TypeScript (including unused checks), production
build, dependency checks and the metadata-only source secret scan passed.
The real browser check found and fixed phone overflow in the RAG diagrams.
The new streaming trace regression advances interleaved users through AnyIO's
thread pool and closes a partial stream without leaking context between users.
Production artifacts exclude the local synthetic fixtures. Server dependencies
were not replaced; optional laptop requirements are in `requirements-exam-scan.txt`.
Passing these checks does not certify OCR or scientific question correctness.

Next: after the saved deadline run the Gemini pilot; compare literal stems, all
ordered options, every critical math symbol and
figure label against original pages. The Groq pilot hallucinated page/layout
details and one printed option, so it is not an accepted OCR path. Do not call
model agreement human verification. Establish a larger held-out gold set and
measure critical-error rates before declaring a scanning model the best.

Review answer/explanation association, continuation pages, mixed-major headings,
figure crops and scientific validity separately. Full structured import is **not
complete**. No new vectors were exported/uploaded, and no deployment was performed.


## Scanning decision and measured pilot

Use native text and layout for searchable evidence, then actual page images and
small question groups for mathematical transcription. Hold uncertainty for
visual review; readability and valid JSON do not prove formula correctness.
The pilot has not established a winning model or a production accuracy rate.

Seven pilot pages include official and compiled mathematics, physics figures,
chemistry and archive material. Four local engines have 28 saved outputs. Cloud
requests used actual PNG inputs, not text-only descriptions of a supposed page.

| Method | Observed use and limitations |
| --- | --- |
| PyMuPDF | Very fast native extraction; preserves spans and coordinates. Plain text broke formula order, fractions, powers and some RTL digits in inspected math. |
| PDFium | Alternative native extraction to compare Unicode/reading order; plain output still does not prove formula structure. |
| Tesseract fas+eng | Approximately 2–8 seconds/page in this pilot. Misread math letters/numbers and fractions; cannot represent physics figure topology reliably as prose. |
| EasyOCR fa+en, laptop GPU | Approximately 5–12 seconds/page after model loading. Useful text regions, but critical formula/option errors remained. Cached models avoided new model downloads. |
| Groq Qwen vision, high reasoning | Whole-page output reached its output limit. A single-question response completed but misread an ordered option and page number; layout responses also hallucinated repeat/crop details. Held out of usable references. Free vision output capacity then rejected high-reasoning requests. |
| Gemini native image endpoint, high reasoning | Direct generation suffered connection resets. The laptop proxy reached the endpoint, then all available keys returned daily request limits. No accepted Gemini accuracy result yet. |

These timings are pilot measurements, not predictions for a 100GB corpus. Character
count is not OCR accuracy. No percentage accuracy is claimed and no local engine
was promoted just because its output looked readable.

## Import identity and storage

- Hash whole files and deduplicate identical PDFs across archives.
- Keep source archive/member aliases; filename is a label, not identity.
- Validate archive member paths and extraction targets; no traversal, absolute
  member paths, symlink following or extraction outside the local data folder.
- Keep imports under ignored `backend/data/exam_examples/` and ignore `mocks/`.
- Never replace the application SQLite database or existing textbook vectors.
- Record publisher, exam year/session, grade and major from actual source
  evidence. Filename guesses remain unconfirmed. Mixed papers need question-level
  classification. Do not treat the 105-question math-physics blueprint as a rule
  for humanities, biology, teacher-admission or old-syllabus documents.

## Quality-first pipeline

1. Inventory and hash documents; distinguish duplicate files from distinct
   editions. Record page count and extraction errors.
2. Compare native PDF extraction engines on representative pages. Retain text
   spans and coordinates even if formulas cannot be represented as plain text.
3. Benchmark available local OCR (Persian+English) and vision transcribers on
   text, dense formulas, tables, diagrams and answer keys. Record model/version,
   settings, latency and actual defects. Readability is not mathematical accuracy.
4. Preserve originals, original page/crop and literal transcription separately
   from normalized search text and inferred design annotations.
5. Use region/page vision for unreliable text, formulas and figures. Compare
   independent extractions on high-risk examples; disagreement is a review task.
6. Associate question boundaries, printed IDs, options and figures, including
   continuation pages. Link printed answers/explanations only with explicit
   exam/section/question identity. Never invent missing answer keys.
7. Validate records and keep uncertain/failed pages in staging. Promote only
   qualified authoring references; extraction alone is not scientific verification.
8. Generate separate style/design context, bounded and filtered by major,
   subject/topic and available source evidence. It does not establish curriculum.

## What to preserve per page/question

Document SHA-256, source/member identity, PDF page and printed page, dimensions,
orientation, original blocks/bounding boxes, engine/model/version, literal text,
LaTeX where supported, uncertainty spans, ordered options, source question number,
figure/crop links, answer provenance and explicit quality/review state.

PDF-native text may have broken Unicode mappings or RTL ordering. OCR may miss
negative signs, powers, subscripts, inequalities and negations. Do not normalize
away these distinctions. Unknown fields remain null, not guessed facts.

## Worker and recovery requirements

Persistent per-page checkpoints, atomic writes, bounded concurrency and one
coordinator for shared output. A disconnected terminal must not restart work.
Workers must skip completed compatible records and preserve partial work.

Load credentials from ignored local env files only. Deduplicate exact keys,
retain their private quota/access history, and never expose values in arguments,
logs, prompts, frontend settings or output JSON. Do not call a text-only client
with images and then accept a text-only response as OCR.

Per-minute limits get bounded backoff and failover. Terminal daily quota/access
errors are not repeatedly probed before their conditions change. Respect actual
provider retry times. A new model can have different limits; another key is not
proof of another project/organization. Pause honestly if usable credentials run
out. No fabricated output, fallback solved question or blank-page success.

## Operational acceptance

Separate counts for inventoried/extracted pages, native-text pages, OCR pages,
structured candidates, cross-checked references, manually checked references,
pending review, provider blocks and failures. "Scanned" must not mean "approved".

Status must report stored counts, worker heartbeat/liveness, next action and
remaining eligible pages. Completeness is measured against the source inventory,
not how many jobs happened to finish. Generate a portable manifest for future
transfer, without raw PDFs or secrets; transfer is not authorized yet.
