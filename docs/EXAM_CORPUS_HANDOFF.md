# Local exam corpus: agent handoff

## Authorization and ownership

Local work only in `C:/Users/Arsam/Desktop/Boom-merged`. The user will authorize
pushing later. Do not deploy, upload/import corpus data or push this work.
Exception authorized 14 October: pause the VM mock pool and privately import its
Groq/Gemini credentials for local scanning; this does not authorize VM OCR.
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
and the three qualified visual pilot references remain intact. At that earlier
check no OCR worker was alive. The visible fleet was started later; read the live
status rather than treating this historical check as current worker state.

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

## Visible workers and restart after closing the laptop

The user explicitly requested visible local workers on 14 October. Double-click
`START-EXAM-WORKERS.cmd` in the repository root, or run it from PowerShell. It
opens a scanner console and a live monitor console; the browser dashboard is
`http://127.0.0.1:8770/`. The launcher reuses a live scanner and an existing
monitor. One coordinator owns three parallel threads and the OS lock, rotating
ready keys. Saved page/question checkpoints survive interruption. This does not
start the legacy textbook OCR workers under `ocr-workers/`.

The launcher defaults to the seven-page quality pilot and the laptop proxy
`http://127.0.0.1:10809`; connect the working VPN first. Set `EXAM_OCR_PROXY` before
launch to use a different proxy. The selected model defaults to
`gemini-3.8-flash`, verified in the provider model inventory and a successful
native high-reasoning image-layout probe. Set `EXAM_OCR_GEMINI_MODEL` to override
it for scanning only; this does not change chat, embeddings or VM configuration.
Gemini 3.6 Flash repeatedly returned overload HTTP 503. One 3.1 Pro credential
probe returned a terminal daily quota refusal and is retained privately; do not
repeat it before the saved provider retry deadline. A layout result is not a
whole question transcript or scientific approval.

The dashboard separates actual stored text/layout pages, full-page OCR,
unique saved question candidates and qualified style references. Worker rows
show document, page, stage, model, credential label, HTTP status and request
age. Waiting has a live coordinator but zero active requests. No keys, prompts,
provider calls or write endpoints are exposed by the monitor.

Closing the scanner console stops that process. Closing only the monitor does
not stop the scanner. Sleep/hibernate/shutdown pauses or stops local computation.
After reopening the laptop and reconnecting the VPN, run the same launcher;
compatible completed work is skipped. An in-flight request may need repeating.
No Windows power setting or login task was changed. Finish and visually check
the pilot before launching the full corpus.

Manual commands from `backend/`:

```powershell
$env:EXAM_OCR_PROXY='http://127.0.0.1:10809'
$env:EXAM_OCR_GEMINI_MODEL='gemini-3.8-flash'
.venv/Scripts/python.exe -X utf8 scripts/import_exam_examples.py scan --provider gemini --workers 3 --limit 7 --watch --live
# Separate terminal:
.venv/Scripts/python.exe -X utf8 scripts/exam_scan_status.py --serve --port 8770
```

Earlier detached worker starts were denied by automatic execution review. The
new visible launcher succeeded under the user's explicit visible-worker request.
Closing an old inactive console was separately denied, so it was left to the
user. Confirm live PID/heartbeat, not just a window or saved phase string.

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

## Visible local fleet and production pause (14 October 2026)

Run `START-EXAM-WORKERS.cmd` from the project root. It opens a visible scanner
console and a read-only status console/dashboard at `http://127.0.0.1:8770/`.
It skips an already live coordinator, resumes compatible saved page/question
parts, and waits for stored provider retry times without making calls. The
current run is a seven-page quality pilot with up to eight simultaneous page
jobs, using both Gemini and Groq. It is not the full 19,233-page visual scan.
All 19,233 native text/layout pages are retained; complete visual OCR and
question/reference counts are separate on the dashboard.

A sleeping/off laptop cannot scan. After waking, reconnect the laptop proxy
(default local port 10809) and run the same launcher. Closing the scanner
console stops its process; closing only the monitor does not stop the scanner.
The launcher uses Gemini 3.8 Flash at high thinking after a successful layout
probe; repeated 503 responses still require cooldown. Groq high reasoning
remains enabled. A 1,000-output-token trial returned truncated layouts, so the
launcher retains a 16,384-token budget for full question transcription. Keys
whose actual vision ceiling is lower stay blocked for that request size. No
truncated output is promoted, and the quality gate must pass before bulk OCR.
`EXAM_OCR_GEMINI_MODEL`, `EXAM_OCR_GROQ_OUTPUT_TOKENS`, and `EXAM_OCR_PROXY` can
be set explicitly before running the launcher. A smaller compatible request
may bypass only a known output-size refusal, never access or daily quota blocks.

The user explicitly authorized pausing the Oracle VM pool. Its existing admin
cancel endpoint was called; saved run state is `enabled=false,status=stopped`.
`POOL_WORKER_INPROCESS=False` was already set; no standalone pool process was
running. A private environment/run-state backup was saved on the VM under
`backend/data/operator-backups/pause-pool-20261014-133112/`. Existing accepted
booklets, pending drafts and account data remain intact. Resume pool production
only when the user asks, through the admin panel's Start control. No code was
deployed and no local corpus was transferred to the VM.

The VM's 16 Groq and 13 Gemini credentials were imported privately into ignored
`ocr-workers/worker-vm/worker.env`. The scanner reads this alongside local envs
and deduplicates exact keys. These counts do not establish independent provider
organizations/projects or usable vision capacity. Actual quota/access responses
determine eligibility. Secrets are never displayed on the monitor or committed.

The scanner validates cached layout/question parts before reusing them. Earlier
schema-invalid cached parts could consume retry allowances without a new request;
validation version 2 permits a bounded fresh attempt for those failures. Complete
valid parts stay reusable, and provider quota/access history is not reset.
OCR regression tests: 83 passed, one skipped.

## Credential rotation follow-up (14 October)

Keys rotate independently per provider; daily/access/capacity refusals only block
the affected identity, without inferring shared quota from other keys. A new
regression test confirms a second Gemini key is used while the first awaits its
daily reset. The daily-quota parser now handles a missing retry hint without
misclassifying it as a transport error. The watch deadline cannot produce a
negative sleep; credential env-file changes wake the wait and reload the fleet
without resetting any saved refusal. Provider work counters distinguish ready
credentials from page jobs held after validation failures.

At inspection, all 13 Gemini credentials had recent server errors (mostly 503),
not evidence of exhausted daily quotas. Seven Groq pilot page jobs were held
after two invalid/incomplete extractions; ten Groq credentials had no provider
block recorded. Eligible credentials do not imply eligible pending page work or
known remaining quota. All originals and completed parts were retained. OCR
regression checks: 87 passed, one skipped.

## Stalled-worker diagnosis and revised pilot (15 October)

All 19,233 native pages are retained. Latest stored counts: two whole-page
candidates from the earlier pipeline, 17 unique question candidates and three
qualified visual style references. These are not teacher/scientific approvals;
no current-pipeline whole page has completed. The monitor now shows retained
complete candidates as its main count and current-version pages separately.

Actual blockers were distinct: Groq reported a hard 1,000-output-token-per-minute
request ceiling; Gemini had earlier 503s and later transport failures; the local
proxy port 10809 was then confirmed unreachable. Key rotation cannot repair that
network failure. The CLI now waits in `waiting_for_network` when all configured
proxy routes are unavailable, rechecking without AI calls or clearing quota.
TCP reachability is a prerequisite, not proof of upstream provider access.
Reconnect the proxy; the watcher resumes automatically and honors saved provider
refusal times. There is no silent switch to direct routing.

A Windows progress-write failure was also observed: replacing a status file
could raise PermissionError while another process read it. Atomic JSON writes
now retry permission/sharing failures for a bounded interval; persistent failures
still propagate and leave the previous checkpoint intact. OCR regression checks:
104 passed, one skipped. The preceding full backend run passed 870 tests, three
skipped, before the three network regression tests were added.

The revised pilot separates literal reading from inferred design. Printed option
labels are separate from values; original question crops and heading context use
separate image parts. A vector-rendered margin reading aid preserves source
glyphs/coordinates while the complete page remains available to check missing
questions. Native spans are fallible aids. Annotation cannot rewrite literals.
Valid older page versions are archived before replacing the active checkpoint.
Bulk visual scanning remains gated on source-faithfulness checks, not schema
validity or request counts. A few promising math/physics examples establish no
calibrated accuracy rate.

The local RTX3060 PaddleOCR-VL-1.5 element-only Transformers trial was not
selected: it omitted an option on q65 and did not finish harder region/full-page
samples. Private outputs and official pinned model files are retained. This does
not evaluate every Paddle layout pipeline or certify cloud alternatives.

Visible scanner output is saved in ignored
`backend/data/exam_examples/scanner-console.log`. Resume using
`START-EXAM-WORKERS.cmd`; the read-only monitor remains on port 8770. Finished
console windows were closed only after inspecting their complete descendant
trees. Active scanner, monitor, Vite and user shells remain. No deployment,
corpus transfer or Git push was performed; the production mock pool stays paused.

## Free-only scanning constraint and pilot changes (15 October)

The user cannot pay for scanning. Do not enable billing, buy credits, add paid
OCR services, or require rented compute. Use local processing and existing
free-tier credentials within their actual quotas. Code cannot determine a
credential owner's billing configuration from the key string; do not claim that
such an inference is possible. No paid fallback was configured.

The launcher now runs two pilot workers with Groq max output 1,000 and instruct
(`none`) reasoning for copying. Inferred annotation retains high reasoning.
Literal questions are extracted before annotation, and a schema-invalid question
does not prevent retaining later valid question parts. A separate complete
literal-page candidate is saved only when ALL layout question IDs are present
and individually schema-valid. It contributes to complete-candidate counts but
never qualifies a style reference by itself. Scientific/human approval is not
inferred from page completion. Previous valid page versions remain archived.

A live compact instruct-mode request finished in about three seconds using 297
completion tokens, but read q68 option2 mass as 23 rather than the visibly printed
33. This is a failed quality sample, not a successful OCR benchmark. Its enlarged
source crop and output are retained under `model-probe/compact-instruct-1000/`.
The subsequent enlarged-option request hit a transport failure when the local
proxy disconnected again. Keep bulk scanning gated on a source-checked benchmark;
do not accept faster schema-valid output merely because it fits free capacity.

Gemini 503 responses now cause a persistent model-service cooldown with increasing
delay and jitter, rather than immediately cycling the same unavailable model
through every key. This is a service-availability gate, never an assertion that
different keys share account quota. Daily quota, access and hard output-capacity
refusals remain independent and preserved. Rejected truncated responses now keep
numeric token costs and finish reasons without raw replies/hidden reasoning.

Validation after the free-profile changes: 878 backend tests passed, three
skipped; the OCR subset has 109 passed, one skipped. The new visible worker was
started at an idle checkpoint and is waiting for the disconnected proxy. Those
tests verify software behavior, not source OCR accuracy; the live numeric-quality
sample above still fails. No claim of a completed bulk scan is justified.

## First complete source-checked page and network routing (15 October)

The VPN was working through system networking while the scanner still expected
a localhost HTTP proxy. Authenticated read-only model endpoints returned HTTP200
for both providers without that proxy. The launcher now defaults
`EXAM_OCR_PROXY=system`, explicitly overriding stale proxy entries in ignored
env files. Explicit HTTP proxy overrides remain supported. This is a routing
correction, not permission to alter VPN or Windows settings.

One entire page is now source-checked: PDF page16 / printed page7 of document
`66b5551fa48873c0621e2a9ed39a6e08fa816bd9d7b0acc41a76fce992aef049`,
questions65–68. A retained complete Gemini candidate was compared against the
full source image and enlarged regions. Nine documented assistant visual
corrections address ordered Latin options, source decimal notation, image-option
givens and repeated page furniture. This is an assisted, corrected transcription,
NOT a fully automatic accuracy benchmark or scientific/teacher approval.

Evidence is in the document's `vision/page_00016.visual.json` and its exact-data
and original-image-hash-bound `.review.json`. `reviewed-page.json` points to
that evidence. The local read-only monitor exposes `/reviewed-page` with the
original full page beside all four questions and the original option crops.
It counts `source_checked_full_pages` separately from current-version OCR
candidates. Seven individual style references are now qualified as visual checks;
all remain `human_reviewed=false,scientific_state=not_checked`.

At the last inspection there were also two current-version complete OCR page
candidates and25 retained question candidates; those counts are not approvals.
The region-by-region free Groq pilot fit capacity but still misread Persian
words/numbers. Its manifest, source crops and failed outputs are retained for
future benchmarks. Bulk OCR therefore remains gated on quality, despite real
candidate progress after correcting the route. OCR regression suite:112 passed,
one skipped. Review endpoints were checked for four questions, five original
PNG routes, source hash binding, and explicit assisted/non-scientific disclosure.

Cleanup removed18 obsolete one-off `tmp/operations` drivers and the unused
1,917,255,968-byte Paddle model weights. Small model metadata and failed-pilot
evidence remain. Original PDFs, successful checkpoints, quota state, reviewed
records, env files, active workers and other agents' changes were preserved.
Finished scanner/monitor consoles were closed only after checking their entire
descendant trees; the read-only monitor now runs hidden with ignored log files.
The user's cleanup and free-only preferences are recorded in AGENTS.md.

### 15 October: expanded local benchmark

The visible launcher now selects30 distinct pages with up to8 concurrent page
tasks, configurable through EXAM_OCR_PAGE_LIMIT and EXAM_OCR_WORKERS. This is
candidate collection for a benchmark, not permission to bulk-import unreviewed
OCR. Scheduling shares available slots by current provider load; unavailable
providers reserve no capacity. Existing seven-page defect holds, completed parts
and all provider cooldowns remain intact. Watch mode also resumes when a saved
retry deadline passes just as a scan finishes, rather than exiting at that race.

The old coordinator was stopped only while waiting with zero active candidates;
the replacement published selected_pages30 and worker_capacity8. Actual requests
resumed. Early Groq responses still include invalid_layout and429, so increased
concurrency is not evidence of increased accurate-page throughput. The OCR test
suite passes113 tests with one skipped; scheduling coverage includes balanced
allocation, a blocked provider, existing in-flight work and a short provider queue.
No VM access, upload, push, billing change or quota-state reset was performed.

### 16 October: independent-key audit and efficient whole-page pilot

The user confirmed all Gemini keys belong to separate projects. Do not infer
shared project capacity from similar errors. A one-time, explicitly requested
generation audit is saved under ignored `credential-audits/20261016T000826Z`.
Its first LOW-thinking probes were inconclusive400s. The actual HIGH profile
returned5 daily-limit errors and8 unsupported-location errors; a changed-route
diagnostic confirmed another individual quota refusal. Unsupported-location
responses do NOT establish remaining quota. Prior refusal state is retained.
Some new responses supplied a roughly24-hour retry hint, which takes precedence
over an earlier assumed Pacific-midnight retry. Never repeatedly probe a known
terminal daily limit before its saved time or a relevant condition change.

The user then explicitly requested efficient models without HIGH thinking.
After their VPN/network change, `gemini-3.5-flash-lite` with MINIMAL thinking
successfully processed the checked physics page. Whole-page calls took5.02–6.64s
and approximately2.8–3.5k tokens; no thinking tokens were reported. These are
single-page observations, not sustainable throughput or corpus accuracy claims.
The first combined prompt took5.7s but falsely labeled physics questions as math.
The new whole-page mode extracts literal evidence only, using a bounded JSON
schema; source-supported/inferred design annotations must be a separate step.

Quality is MIXED and not approved for unattended import. All four question IDs,
main numerical givens and figure-option masses14/33/46/37 were captured. However,
whole-page responses reversed/left ambiguous RTL Latin-letter options and
changed printed slash decimals to commas. A focused source crop recovered the
four correct logical option sequences in3.88s, but added an unsupported
split-rings/commutators description. Source crops and failed outputs remain
retained. Schema validity does not approve scientific/source correctness.
Evidence, source hashes and the explicit failed checks are in ignored
`model-probe/efficient-whole-page/gemini-3.5-flash-lite/quality-review.json` and
the read-only `http://127.0.0.1:8770/efficient-pilot` report. The reference text
was never sent to the model. The focused crop used a reviewed bbox, so it is not
evidence of an entirely automated region-repair pipeline.

The visible launcher now uses Gemini-only whole-page MINIMAL processing,
8192 output-token ceiling,30 task slots and a30-page candidate benchmark.
All13 Gemini keys were independently used in the restarted run. Outputs remain
unreviewed literal checkpoints; no automatic qualified style/answer promotion.
Ambiguous Latin option lists without explicit ordering are held by validation.
Model/method/thinking/output profiles isolate caches, preventing old HIGH/model
results from masquerading as an efficient-model benchmark. Original checkpoints
are preserved. Auto routing uses the known laptop10809 proxy when listening,
otherwise the system route; explicit EXAM_OCR_PROXY overrides still work.

New append-only `vision-requests.jsonl` records each attempted request and its
completion, anonymous key fingerprint, model/thinking, HTTP status and numeric
usage. It excludes keys, prompts, source images, reply text and hidden reasoning.
This ledger begins with this change; it cannot reconstruct earlier consumption.
OCR regression coverage includes profile isolation, minimal/disabled thinking,
single-call whole-page processing, bounded schema, ambiguous option holds,
review HTML escaping/source binding and accounting privacy. No paid service,
VM change, push or corpus transfer was performed. Other agents' files remain
untouched; finished owned scanner consoles were closed after tree checks.

The bounded30-page efficient benchmark subsequently completed:24 page
checkpoints saved,6 held after validation,39 API attempts across all13 distinct
Gemini keys, all with MINIMAL thinking. These are checkpoint/format results,
not24 source-approved question pages. The final monitor counted21 current
complete-page candidates,26 retained candidates and153 question candidates;
source-checked full pages remain1. No automatic corpus-wide launch was made.
The completed benchmark console was closed; the read-only monitor remains on.
Validation after these changes:918 backend tests passed,3 skipped; explicit
own-source secret scan and diff whitespace check passed. Resume instructions:
START-EXAM-WORKERS.cmd runs the same30-page minimal whole-page benchmark and
reuses only compatible profiles; do not expand to the full corpus until the
source-faithfulness issues and a representative benchmark are addressed.

## Free local OCR comparison (16 October 2026)

The user requested a DeepSeek-OCR installation/test and other free scanning
options. This is an isolated local pilot, not permission to publish a corpus or
change production. The existing Windows Ollama runtime is used so the backend's
Torch/Transformers dependencies do not need to be replaced. DeepSeek-OCR's
upstream code and model are MIT licensed. The library's `3b-bf16` model is about
6.7 GB; this laptop has a 6 GB RTX 3060 and 16 GB system RAM. GPU memory and
available system RAM must be measured during inference; published A100 numbers
are not laptop estimates. Local inference has no API quota or service fee.

Reusable bounded pilot, from the repository root:

```powershell
ollama pull deepseek-ocr:3b-bf16
backend/.venv/Scripts/python.exe -X utf8 backend/scripts/benchmark_local_ocr.py --engine deepseek
backend/.venv/Scripts/python.exe -X utf8 backend/scripts/benchmark_local_ocr.py --engine tesseract --psm 6
```

Ollama must be running locally. The script refuses cloud names and remote
aliases, checks that the model is installed, uses only localhost with proxy
inheritance disabled, and preserves source/input hashes, model digest, settings,
partial/final text and runtime metrics in ignored `model-probe/local-ocr/`.
`--image` supports another local page image; `--crop x0,y0,x1,y1` records manual
region selection rather than presenting it as automatic layout discovery.
`--prompt markdown` uses the upstream document prompt; `free` is the default.
An HTML view displays escaped output beside the actual OCR input. It never
executes model HTML/coordinates or imports the output into qualified examples.
Token limits/deadlines retain failed evidence; reaching a token limit is not a
successful complete scan. None of the results is automatically source-approved.

Tesseract 5.4.0 with the installed `fas+eng` models took 1.704s (PSM3) and
1.541s (PSM6) on the checked physics page. Both produced critical errors in
question identifiers, values/units and diagram labels. A separate pinned
`tessdata_best` comparison took 2.859s (PSM6), still with critical errors.
Its Persian model hash was identical to the installed Persian model; the
English model differed. Results and provenance are retained, not promoted.
These are selected-page timings, not corpus-wide accuracy or throughput.

Other free candidates researched, not yet source-benchmarked here:

| Approach | Useful role | Main constraint |
| --- | --- | --- |
| Existing native PDF extraction + original page/figure crops | Fast first pass; retains layout evidence without generative transcription | Native text on the checked page reverses some numbers and loses math glyphs despite valid Unicode. `needs_ocr=false` is not source approval. |
| Tesseract + OCRmyPDF | Lightweight searchable text layer for plain Persian prose | Our test failed critical math/diagram data. A searchable PDF does not provide reliable figure semantics. |
| PP-OCRv5 Arabic/Persian recognizer (`fa`) | Dedicated text recognition; promising next lightweight baseline | Different from the previously failed PaddleOCR-VL pilot; still needs layout/formula/figure handling and a real Persian exam benchmark. |
| Surya | Local OCR, layout, reading order and table parsing; current model about 650M parameters | Code Apache 2.0; model weights have modified OpenRAIL terms, free for personal/research/startups below its stated threshold. Vendor Persian results are not our exam accuracy. Windows inference setup also needs checking. |
| MinerU basic / ONNX | Local document decomposition; current basic tier advertises small models and CPU support | This laptop is below its full CUDA tier's 8 GB VRAM guidance. Check Persian results and model licenses; current code license adds service attribution and commercial threshold terms. |
| Docling / Granite-Docling | Structured layout/formula/table candidates on modest hardware | Toolkit MIT, model licenses separate. Granite 258M lists English and experimental Arabic, not verified Persian exam support. |

Prefer a hybrid after a representative benchmark: native text/geometry where
faithful, local recognizer for uncertain prose, original crops for all figures,
and targeted vision repair for equations/reading order. Record disagreements
and hold critical failures. Do not rewrite original notation or use a model's
guessed answer to validate a transcription. No claimed OCR accuracy percentage
should be inferred from one selected page or a vendor benchmark.

Primary references checked for this comparison:

- https://github.com/deepseek-ai/DeepSeek-OCR
- https://ollama.com/library/deepseek-ocr
- https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html
- https://github.com/tesseract-ocr/tessdata_best
- https://ocrmypdf.readthedocs.io/en/latest/introduction.html
- https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.md
- https://github.com/datalab-to/surya (including MODEL_LICENSE)
- https://github.com/opendatalab/MinerU (including LICENSE.md)
- https://huggingface.co/ibm-granite/granite-docling-258M

### Restarting a completed batch

The original launcher selected the same 30 pages on every start. Once 24
candidate checkpoints were saved and 6 exhausted validation retries, a restart
correctly found zero pending work and made zero requests, but the terse console
looked like a broken restart. Of those 24 checkpoints, 23 are question pages and
one is a cover page. The retained 26 question-page candidates also include
older attempts and must not be compared directly with a 30-page current batch.

`START-EXAM-WORKERS.cmd` still resumes the saved batch. To explicitly extend the
evaluation to the next 30 selected pages, run `START-EXAM-WORKERS.cmd next` from
the repository root. This uses a saved offset, requires the preceding batch to
be complete, preserves held/completed evidence, and does not start an unbounded
full-corpus scan or automatically approve any new output. The CLI equivalents
are `scan --limit 30 --next-batch` and `scan --limit 30 --offset 30`, with the
usual provider/model/method profile. Live completion messages now explain this
instead of dumping the entire credential-health JSON. Dashboard labels separate
selected batch pages, candidate checkpoints, current question-page candidates,
retained history and source-checked pages.

### DeepSeek setup handoff — not yet an OCR result

The stock Ollama download failed twice, most recently near6.09/6.69GB.
Its allocated partial file size is not proof of a completed/verified model.
Partial blobs and part checkpoints remain in the user's existing Ollama cache.
The default server was started without HTTPS_PROXY; a direct DNS failure and
later download failure prevented installation. The proxy was subsequently
confirmed reachable, including an actual ranged model download request.
Automatic approval review rejected both restarting that server with proxy
settings and starting a separate isolated server, returning only `blocked by
policy`. No alternative process-control workaround was used. The user was
asked to quit the Ollama tray app and manually run, in Command Prompt:

```bat
set HTTPS_PROXY=http://127.0.0.1:10809
set NO_PROXY=localhost,127.0.0.1
set OLLAMA_HOST=127.0.0.1:11434
ollama serve
```

For PowerShell, use environment assignments instead of CMD's `set` syntax:

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:10809"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_NO_CLOUD = "1"
ollama serve
```

The user's first manual restart listened successfully but its log showed an
empty HTTPS_PROXY because CMD commands had been pasted into PowerShell. The
correct PowerShell commands were supplied; wait for confirmation that the log
actually contains the proxy before repeating the model download.

After the user confirms the server is listening, resume the saved partial
download and run the bounded OCR pilot:

```powershell
backend/.venv/Scripts/python.exe -X utf8 backend/scripts/benchmark_local_ocr.py --engine deepseek --pull
```

The runner's `--pull` saves numeric download progress and sanitizes server
errors so signed download URLs are not put into reports. A bounded local-model
wait expired without installation; it has exited. No DeepSeek inference,
Persian accuracy, GPU fit or throughput claim is justified yet. Actual setup
state and commands are saved in ignored `model-probe/local-ocr/setup-resume-notes.json`.
The higher-accuracy Tesseract comparison weights were removed after their
unsuccessful comparison; their license/provenance and all result evidence are
retained. The existing installed Tesseract models were not changed.
Latest focused validation:159 passed,1 skipped; monitor JavaScript compiles.
No VM access, paid service, push or application dependency changes occurred.

### Wi-Fi / proxy interruption recovery

Recovery fixes now preserve the selected batch offset on an ordinary restart
(including an explicit offset0 override), and clear inherited `next` launcher
flags. A worker originally launched with `next` can no longer accidentally
advance again instead of resuming after an interruption. During a running scan,
an unavailable configured proxy pauses new dispatch, drains in-flight work and
keeps the pending queue. The watch coordinator waits for that same proxy route
to return instead of silently switching direct when auto resolution changes.
Successful page checkpoints remain unchanged. Transport refusals do not consume
the two document-validation attempts or turn pages into corrupt examples.

Connection/network errors now show `paused` with a short30-second retry, not a
misleading failed-page state. Connection/pool establishment has a10-second
timeout; the longer300-second model-response timeout is retained. Daily quotas,
authentication denials and provider retry times remain separate and are never
cleared as a network recovery shortcut. No OS auto-start/service was installed.
Keep the laptop awake and the worker terminal open. A powered-off machine does
not scan; rerun the ordinary launcher after waking to resume its saved batch.

Tests simulate connection resets, a proxy disappearing after a saved page,
preservation of a second key's daily quota and saved-batch restart behavior.
Latest focused result:163 passed,1 skipped. The running coordinator was checked
to have started after the recovery changes; the dashboard responded HTTP200.
The DeepSeek download is a separate local setup client. Its earlier attached
client ended without a completion record; a detached client now writes only
sanitized progress to `model-probe/local-ocr/deepseek-client.*.log` and records
its result in the usual per-run folder. It still must finish installation,
verify the full model digest and run actual OCR before any quality claim.


### 18 October: operator controls and recovery verification

Read `docs/SCANNING_OPERATIONS.md` for commands valid from any directory.
The launcher now supports `status`, `monitor`, `stop`, and `proxy URL`.
The default launcher pins local proxy10809 instead of silently falling direct
when its listener disappears. An ignored scanner-settings.json supports explicit
proxy reloads while waiting or after active requests drain. Stop requests drain
active requests and preserve pending pages; a normal launch resumes that batch.
Unknown exceptions are reported as failed with a sanitized exception type, not
restarted forever. No service or boot task was installed.

At inspection, offset180 had completed28 saved candidates and2 held pages, with
no live scanner. Started the next bounded30-page batch at offset210;21 new
candidates saved. Verified live safe stop:21 saved,9 pending,0 active, process
exited. Normal restart reused all21 checkpoints at the same offset210 and
retained the9 pending pages. Provider quotas were not cleared. The dashboard
was restored on port8770. Current state can change; read the live monitor.

Validation:174 passed,1 skipped across exam_recovery_test.py,
exam_corpus_test.py and local_ocr_test.py. Includes real local TCP connection
refusal followed by a successful synthetic endpoint request with a fresh client,
proxy-change recovery while waiting, stop during cooldown/network wait and
mid-batch queue/checkpoint preservation. Did not disrupt the system VPN.
Dashboard JavaScript compiled. Saved OCR is still candidate evidence, not human
or scientific review. No VM, push or paid services used.


### Automatic continuation authorized

User explicitly requested successive batches without manual intervention and
unattended day-long operation. Normal launcher now passes `--auto-next`; it
resumes saved offset, advances only after selected_scan_finished with no pending
or active pages, and terminates at a zero-page end sentinel. Stop is checked
between batches. No OCR output is automatically reviewed or approved. Windows
idle system sleep is inhibited during the coordinator lifetime and restored on
exit; explicit sleep, closing the lid, reboot or terminal close still interrupts.
177 focused tests passed,1 skipped, including final partial batch, end-of-input,
stop-between-batches and refusal/incomplete-batch non-advancement.
