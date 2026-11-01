# S0 task board

22 October 2026. Sole integrator: Sol. Contract: CONTRACTS.md v0.1; reasoning vocabulary candidate 0.1. S0 is complete for documentation and ownership. Current status is summarized below and in the dated handoffs; browser checkboxes are not evidence of implementation or approval.

## Current evidence

Read-only checks of saved batch-5000-v1 JSON: 4,824 pages, 17,605/17,605 vectors. Retrieval pilot: six queries for three math items; Recall@5 / MRR dense 1/1, hybrid .6667/.3333, reranked .3333/.2083, BM25 .3333/.0833. This is a small development regression, not a production policy decision. release-readiness.json ready=false, automatic_activation=false: independent sources, subject coverage, retrieval/generation acceptance and reviews are missing. No live workers or provider health were tested.

## Ownership and dependencies

Only Sol edits this board and shared contracts. All current dirty/untracked paths below are reserved existing work; no ownership transfer is implied. Freebuff may report issues anywhere but writes only assigned new files. Stop before overwriting an existing path and request a new assignment from Sol.

| Task | Owner | Writable paths | Depends on | Status / evidence |
| --- | --- | --- | --- | --- |
| S0 | Sol | this board, CONTRACTS.md, README.md | none | complete; source inspection and checks below |
| F0 | Freebuff | docs/production-work-pack/FREEBUFF_HANDOFF.md | none | complete with audit caveats below |
| H0 | User | private authoring_work/source-identity decisions | none | complete for source identity; combined Maze booklet inspected |
| S1a | Sol | exam_source_packets.py; prepare_maze_source_packet.py; related tests and private packets | S0,F0,H0 | complete for packet preparation; see S1A_HANDOFF.md |
| ST | Sol | reasoning_tags.py, reasoning_tags_test.py, fixtures/reasoning_tags, REASONING_TAG_CONTRACT.md | S0 | complete; draft validator and fixture; 26 related tests passed |
| F1 | Freebuff | backend/scripts/validate_exam_review_inputs.py; tests/exam_review_inputs_test.py; tests/fixtures/authoring_source_contract/*.json; own handoff | S0,F0 | accepted 23 October; 48 tests passed |
| F2 | Freebuff | frontend/src/authoringReview/*; frontend/authoring-review-tests.mjs; own handoff | S0,ST | accepted23 October;17 tests,TypeScript and scoped browser QA passed |
| F3 | Freebuff | tests/authoring_adversarial_test.py; tests/fixtures/authoring_adversarial/*; own handoff | ST,H2 | blocked; fixtures and offline harness only |
| H1 | User/expert | private curriculum/split decisions | S1a,F1 | user decisions recorded; split sealing/exposure checks pending |
| S1b | Sol | source_routing.py; HybridSearch/style/chat/planner wiring; split/preflight scripts | H1,S1a,F1 | implemented locally; evidence/activation gates in S1B_HANDOFF.md |
| SR / H2 | Sol / expert | authoring_review store/router/server; F2 live adapter and tests / private human decisions | S1b,F2,ST / SR,H1 | SR integrated locally; H2 pending; see SR_HANDOFF.md |
| HA / F4 / HT | User models / Freebuff / human | private annotations / comparison / decisions | H2,ST / HA / F4 | local merged candidate prepared; human label calibration pending |
| S2 / S3 | Sol | constructors, generation, quality and bank lifecycle | HT,S1b,H2 / S2,F3 | S2 experimental sandbox implemented; production S2 and S3 acceptance pending |
| S4a / H3 / S4b | Sol / expert / Sol | evaluation / private judgments / integration | S3 / S4a / H3,S3 | pending |
| F5 / SQ / H4 | Freebuff / Sol / users | QA assignment later / fixes / private pilot | S4b / F5 / SQ,H3 | pending |
| S5a / H5 / S5b | Sol / user / Sol | release candidate / explicit decision / later authorized rollout | H4 / S5a / H5 | pending; no rollout authorization |

All existing backend/frontend files, shared schemas, dependencies, DB/config and monitor/router wiring remain Sol-owned integration surfaces. Preserve concurrent work; inspect diffs before every integration. F1-F3 must not import app startup or invoke providers. Paths reserved above do not authorize starting a blocked task.

## Initial scoped pilot and evaluation protocol

Begin with one human-identified grade-12 math-physics questions/answers pair; preserve source hashes and booklet/session association. First review 20 source questions, including at least five figure-dependent items if available; do not invent coverage to meet counts. Expand toward 300 reviewed items and 10–15 families only after the slice works. Initial taxonomy pilot is at most 50 development items.

Before tuning, H1 seals whole papers and related variants with hashes and split ownership. Holdout selection and curriculum version await human confirmation. Development regressions include weak extreme trig and contradictory quadrant draft; they are already exposed and cannot be holdout items.

Compare baseline versus design-conditioned generation on the same frozen development specifications: proposed 20 items per condition, balanced across supported levels/topics, then blinded expert review in randomized order. Count attempted, held, failed and accepted; record critical correctness, unique answer, curriculum, figure fidelity, novelty, exam likeness, tier fit, latency and tokens per accepted item. Expert rubric/raters and acceptance of subjective likeness are pending H1/H3; no approval invented. Zero unresolved critical defects per released item. Freeze policy before final holdout evaluation; one final test, then exposed failures move to development and require replacement holdouts.

Retain current release minima: 20 source questions, three held-out documents, math/physics/chemistry, 30 retrieval queries, Recall@5 >= .9, MRR >= .8, 20 verified generation items. A math-only pilot cannot qualify a full 105-question mock. These are minimum project gates, not statistical guarantees.

## Real gaps and obsolete guidance

- Question/answer pairing and attributed identity decisions are not evidenced complete; H0 required.
- Representative retrieval, three-subject coverage, reviewed source/curriculum/science/novelty and calibrated demand remain blocked by saved readiness.
- Exact image equality and independent receipt dimensions need later adapter enforcement; current source_image hash presence alone is insufficient.
- Difficulty gate vocabulary conflates reviewed intended tier and measured empirical difficulty; ST/SR must resolve explicitly.
- AGENTS.md test counts and embedding-provider defaults are historical, not current measured results/configuration. EXAM_CORPUS_HANDOFF early five-key quota, seven-page launcher and port8770 paragraphs are dated history; never clear quota state based on them. No bulk doc cleanup in S0.
- Partial-corpus retrieval numbers in EXAM_QUALITY_RELEASE are superseded by its dated full-snapshot section; still only six queries. QUESTION_DESIGN_SCHEMA remains proposed and must not overwrite flatter existing records.

## Exact F1 starting instruction

After completing F0, read CONTRACTS.md v0.1 and your F0 handoff. Implement only backend/scripts/authoring_source_validator.py, tests/authoring_source_validator_test.py and synthetic JSON under tests/fixtures/authoring_source_contract/. Build an offline CLI accepting an explicit manifest path and optional local base directory, with machine-readable diagnostics and nonzero exit on structural errors. Separate schema errors from evidence/eligibility holds. Validate PDF roles, explicit pair mappings by session/booklet/section/printed number, SHA shape and optional streamed file verification, one-based PDF pages, normalized ordered bboxes, continuation references, option order and 0-based answer bounds, revision/hash-bound receipts and stale evidence. Unknown provenance must remain held; never infer pairing from filenames or equal page offsets. Include valid structural-but-held synthetic examples and negative duplicate mapping, ambiguous key, out-of-range bbox/page, traversal and stale-receipt cases. Keep all imports stdlib; do not import app modules, open the application DB, scan PDFs, call providers or activate anything. Do not edit core modules/shared schemas/dependencies. Verify any real output destination is ignored. Run the new focused tests and CLI on synthetic fixtures, then write FREEBUFF_HANDOFF.md with files, exact results, unresolved contract questions and proposed integration points for Sol. Stop before wiring.

## S0 evidence and working-tree baseline

Commands: git status --short; static reads and rg of source/import, quality/style/generation and mocks claim code; stdlib JSON aggregate reads of frozen status/retrieval/readiness; git check-ignore backend/data/authoring_work/example.json confirmed ignored. No application imports or runtime tests, migrations, provider calls, scans or embedding. Source paths include backend/app/rag/pool_core.py (not routers/pool_core.py). The initial wrong-path rg was corrected in the documentation; it caused no writes.

Pre-S0 dirty status follows. This is a preservation inventory, not a claim of reviewing/approving every line:

```text
 M START-EXAM-WORKERS.cmd
 M backend/app/rag/chunking.py
 M backend/app/rag/exam_control.py
 M backend/app/rag/exam_scanning.py
 M backend/app/rag/mock_generation.py
 M backend/app/rag/question_quality.py
 M backend/scripts/benchmark_local_ocr.py
 M backend/scripts/exam_scan_status.py
 M docs/EXAM_CORPUS_HANDOFF.md
 M frontend/emoji-free-tests.mjs
 M frontend/src/App.tsx
 M frontend/src/components/Experience.tsx
 M frontend/src/components/StudyDeskHero.tsx
 M frontend/src/components/StudySymbols.tsx
 M frontend/src/desk.css
 M frontend/src/navConfig.ts
 M frontend/src/pages/Home.tsx
 M frontend/src/pages/Profile.tsx
 D frontend/src/pages/Streak.tsx
 M frontend/src/profileSync.ts
 D frontend/src/studyStats.ts
 M frontend/src/types.ts
 M frontend/study-desk-tests.mjs
 M tests/local_ocr_test.py
?? backend/app/rag/evaluation_cache.py
?? backend/app/rag/exam_candidate_index.py
?? backend/app/rag/exam_quality.py
?? backend/app/rag/exam_quality_view.py
?? backend/app/rag/question_design.py
?? backend/scripts/audit_exam_snapshot.py
?? backend/scripts/benchmark_exam_chunking.py
?? backend/scripts/download_deepseek_ocr.py
?? backend/scripts/evaluate_exam_generation.py
?? backend/scripts/evaluate_exam_retrieval.py
?? backend/scripts/exam_release_status.py
?? backend/scripts/stage_exam_embeddings.py
?? docs/EXAM_QUALITY_RELEASE.md
?? docs/QUESTION_REASONING_TAXONOMY.md
?? docs/production-work-pack/
?? tests/chunking_quality_test.py
?? tests/evaluation_cache_test.py
?? tests/exam_candidate_index_test.py
?? tests/exam_quality_test.py
?? tests/exam_quota_recheck_test.py
?? tests/exam_release_status_test.py
?? tests/question_design_test.py
```

Next handoff: F0 can run immediately; user H0 can identify a pair in parallel. F1 starts only after F0. Sol next starts S1a after F0/H0, or ST independently after S0. No later stage was executed here.

Final S0 validation: synthetic JSON parsed; Markdown fences balanced; reserved helper paths confirmed unused; git diff --check passed (only an existing line-ending warning). Static read confirmed backend/app/rag/pool_core.py uses the shared pool logic and four difficulty levels. No runtime quality claim is made.

## Phase 0 completion audit — 22 October 2026

S0, F0 and H0 are complete for their bounded baseline/identity deliverables. Later scientific review, per-question answer association and source qualification remain pending. This does not activate corpus data.

F0 handoff exists and provides gaps, proposed paths and an F1 handoff. Accepted as inspection evidence with corrections: CONTRACTS.md exists; TASK_BOARD.md belongs in this directory, not repo root; its 300/2 and frontend 4/4 totals are historical/unsubstantiated here and must not be presented as fresh test evidence. Do not use its palette suggestions to expand F1. The Freebuff-owned handoff was preserved.

H0 evidence: ignored backend/data/authoring_work/h0/source-identity.json and rendered covers page-1.png/page-23.png. Original PDF remains on Desktop. Locally read PDF has 97 pages; question and answer covers match Maze, stage20, 1403/04/07, A and control121. Page23 is the answer booklet cover, not the first worked solution. User confirms mock classification. No question-level pairing/scientific approval claimed; grade remains unknown.

Next ready tasks: Sol S1a (source packets/pairing), Sol ST (annotation contract), and Freebuff F1 using the exact instruction above. Coordinate writable files; F2 still waits for ST.

## S1a handoff — 22 October 2026

Status: partial, source-packet foundation implemented; detailed real answer mappings remain held. Sol owns new backend/app/rag/exam_source_packets.py and tests/exam_source_packets_test.py. Existing import formats/snapshots and Freebuff files were preserved. No F1 patch exists at inspection, so none was integrated.

Implemented explicit identity joins (exam/session/booklet/section/printed number), duplicate/ambiguous/missing key holds, unresolved continuation holds, source/content hash requirements, both-side receipt binding, deep-copied versioned packet deltas and unapproved split candidates. Successful joins are linked_candidate, never eligible or scientifically verified. This is a callable sidecar API, not automatically wired into existing scanners.

Private evidence: backend/data/authoring_work/s1a/status.json points to immutable hash-named packet; native-pages holds 97 page candidates from the unchanged chosen PDF. Matching source SHA checked against H0. Covers at pages1/23 establish combined booklet identity; page role boundaries beyond covers are inferred. Per-question regions, printed numbering across all sections, answer keys and publisher labels have not been fully resolved: verified mappings=0, scientific reviews=0. No extraction accuracy claim. The exposed paper is proposed for development only; final split approval and duplicate/compilation/family checks remain H1 work. Native formula extraction is unreliable and cannot serve as a scientific transcription.

Actual checks: pytest tests/exam_source_packets_test.py: 5 passed; git diff --check passed with existing line-ending warning; private status destination confirmed ignored. No provider calls, embedding, migrations, retrieval routing, production activation, push or VM work.

Next S1a continuation: use preserved page candidates/rendered source to resolve and hash question/answer regions, including distributed section samples and continuations; preserve publisher difficulty/type/subject as attributed labels. Supply explicit records to pair_questions, inspect all holds and save versioned packets. Do not call this mapping complete based on covers or native numbering. F1 may proceed independently; Sol reviews its patch before integration. H1 can inspect proposed source/split metadata but must not approve unresolved question associations.

ST ownership: Sol reserves backend/app/rag/reasoning_tags.py, tests/reasoning_tags_test.py, tests/fixtures/reasoning_tags/ and docs/production-work-pack/REASONING_TAG_CONTRACT.md. No Freebuff-owned files are edited.

ST complete: see REASONING_TAG_CONTRACT.md for implemented equivalent validator, fixture, actual checks and limitations. F2 prerequisite ST is satisfied; no bulk annotation, approval or production integration.

Phase1 audit: incomplete. S1a status still review_pending, zero verified answer mappings. ST tests pass (combined run: 22 passed outside F1). F1 exists at backend/scripts/validate_exam_review_inputs.py, differing from handoff named path; tests/exam_review_inputs_test.py rerun: 6 failed, 1 passed, 2 errors. Test defects include undefined save_json, nonexistent tests/validate_exam_review_inputs.py subprocess path and run_validator positional signature mismatch. Freebuff must correct these at its existing owned paths and reconcile its handoff before integration acceptance; no edits to its implementation were made in this audit. Do not mark F1 or S1a complete.

S1a continuation completed packet preparation:105 questions,105 worked answers,105 author-key/label candidates;65 explicit continuation holds,40 linked candidates; no source/scientific approvals. See S1A_HANDOFF.md for evidence and exact review limitations.25 focused tests passed. Earlier partial/zero-mapping paragraphs are historical, superseded by this dated handoff. Phase1 still awaits F1 fixes/acceptance.

F1 recheck: test collection currently fails at tests/exam_review_inputs_test.py:27 because annotation Any is not imported. No tests execute. Script path was corrected since prior audit, but F1 remains unaccepted. Handoff still contains obsolete missing-CONTRACTS claim and old file names. Static inspection also shows provenance index uses int conversion (accepts coerced values/can raise), and receipt validation needs demonstrated cross-record hash/revision binding before acceptance. Preserve Freebuff ownership; send these findings back for correction.

F1 audit 23 October: existing suite now 9 passed,1 warning (subprocess UnicodeDecodeError reader thread). Still unaccepted: direct synthetic check_question_sidecar probe accepts pdf_page0 and bbox[2,2,-1,-1] with zero diagnostics. Receipt checker only required fields/outcome/schema, no cross-record content/image/revision comparison. Manifest partition calls .get before malformed-type guards. CLI lacks assigned base-directory containment and default structural-error failure (strict opt-in only). Handoff remains stale. Fix acceptance gaps and add adversarial tests; green existing suite alone is insufficient.

## F1 acceptance — 23 October 2026

Fresh rerun:48 passed, no warnings. Direct previously failing page0/reversed-out-of-range bbox probe now emits structural diagnostics. Test coverage includes malformed manifests, strict integer answer indices, path containment, stale content/image receipts and unbound revisions. Updated handoff describes actual paths and limitations. Accept F1 as bounded offline validator; no live import/router wiring performed. Structural errors fail by default; unresolved evidence is held and --strict also fails holds. This is intentional, not approval. Actual implementation/test filenames above supersede originally reserved names. S1a packet preparation, ST draft contract and F1 bounded validator now satisfy Phase1 deliverables; subsequent source reviews and H1 split/curriculum decisions remain pending.

H1 user decisions 23 October: all supplied textbooks accepted as current; math-only pilot; H0 Maze paper for development; five newly designated Maze PDFs reserved for evaluation; existing data/raw/plans schedules selected. Private versioned receipt: backend/data/authoring_work/h1/decisions-v1.json binds catalogue and files by SHA. Catalogue snapshot411 nodes/28 books. All five evaluation PDFs already have1,008 frozen candidate records collectively; existing indexing is not proof of prompt exposure, but no clean unseen/sealed claim is supported yet. S1b must enforce exclusions and audit prior exposure/duplicate families before final split freeze. No holdout questions/answers were opened for this receipt. No extra user action currently required. H1 final split gate remains pending; S1b may prepare exclusion/audit mechanics without claiming completed H1.

H1 additional source candidates23 October:5 new mocks subfolders contain10 PDFs; all10 byte hashes absent from existing exam inventory. Saved ignored h1/new-source-reservations-v1.json; file-byte hashes only, no PDF content inspected. Treat as reserved evaluation candidates, not proof of semantic uniqueness. Filenames suggest question/answer pairs; fifth folder a.pdf role unresolved. Existing scanner/inventory was not started or changed; this reservation is a planning sidecar pending S1b enforcement and cover-only identity checks.

F2 audit23 October:12 tests passed, TypeScript exit0; integration acceptance blocked by receipt contradictions and incomplete question/source/image/catalogue binding. See F2_REVIEW.md for reproduced defects and exact Freebuff correction prompt. Browser QA remains pending after fixes.

F2 accepted after fixes: see F2_REVIEW.md dated acceptance. Server wiring/authorization and real-corpus review remain SR tasks.

S1b23 October: strict purpose-enabled text routes implemented and tested; H1 scope and conservative exclusion manifest frozen. Older reserved sources have saved development reference exposure; newer PDFs remain evaluation candidates with semantic overlap/identity review pending.0 eligible records/0 reviewed Maze scope; no approval invented.284 integrated tests passed/1 skipped, final14 chat/routing tests passed; F1 preflight0 structural errors/106 holds. See S1B_HANDOFF.md for limitations, including unmigrated vision/question-bank channels and unbenchmarked scoped ranking. Do not mark full system isolation or release ready.

Final S1b hardening: strict policy now covers question-bank text and image candidates too; stale/unbound image bytes cannot enter vision.293 tests passed/1 skipped. Earlier unmigrated-channel limitation is superseded. Data acceptance remains held:0 eligible reviewed records,0 reviewed weekly scopes; new evaluation PDFs need controlled semantic overlap/identity qualification. User has no new file-supply task. Local only; no deployment.

HA pass-A24October:14 development-only annotations and inferred design sidecars
prepared with immutable source/crop/catalogue bindings;13 proposed book-backed
mappings and1 unmapped item.22 reasoning-pilot/contract tests passed. All14 draft
answer choices match publisher keys (sanity check only). Independent annotations
and human tag calibration pending; no eligibility promotion or S2 activation.
See HA_HANDOFF.md and TAXONOMY_CALIBRATION_PROPOSALS.md. Writable Sol paths for
this pass: backend/scripts/prepare_reasoning_pilot.py, tests/reasoning_pilot_test.py,
these handoffs and ignored reasoning-pilot-v1 outputs. Freebuff's existing files
are unchanged; any independent annotation output belongs in a new ignored
reasoning-pilot-v1/independent-pass-b folder, without application code changes.

25October external comparison: one user-supplied Claude prose report covering40
items is received and preserved, not silently qualified as schema-valid or
procedurally independent.14 shared cases compared;40 publisher keys align;
27 comparison/pilot/taxonomy tests passed and eight bounded checks reproduced.
See CLAUDE_COMPARISON_HANDOFF.md. Human calibration remains targeted to label
meaning, endpoint interpretation and curriculum-valid default methods. No source
or label approval inferred; no generator activation. Sol-owned new files:
backend/scripts/compare_annotation_reports.py, tests/annotation_comparison_test.py,
this handoff and ignored reasoning-comparison-v1 artifacts. Other agent files and
frozen passA outputs are unchanged.

25October reconciliation: user-authorized combined40-item candidate prepared.
33 relevant tests passed;40 structurally valid annotations,39 proposed existing
book-backed mappings and1 unresolved mapping. Three taxonomy gaps stay explicit;
no registry change or approval inferred. Q15 answer4 retained under publisher's
closed-interval convention; not marked as a key error. See MERGED_REASONING_HANDOFF.md.
Sol paths: backend/scripts/merge_reasoning_reports.py, tests/reasoning_merge_test.py,
this handoff and ignored reasoning-merged-v1 artifacts. No source/checkpoint/receipt
rewrite, provider calls, activation or deployment.

## Local Phase 3 sandbox — 25 October

Eight unpublished specification-derived math questions are ready; see
[S2_SANDBOX_HANDOFF.md](S2_SANDBOX_HANDOFF.md). 62 relevant tests passed;
79 formulas rendered successfully. Desktop preview has eight cards/32 options
and no horizontal overflow. Zero provider calls, zero eligible records and
zero new human approvals. Difficulty buckets are absent in this trial.
Next gate: human judgment of Konkur style, clarity and originality. Older
statements that no S2 work has started are superseded only for this sandbox;
production S2, review/calibration and release gates remain incomplete.

25 October follow-up: live Groq gpt-oss-120b synthetic-scope pilot saved four drafts; three mathematical rejections and one editorial hold, zero eligible. Added conservative structural-copy screening and a local typed-spec constructor adapter.186 tests passed/1 skipped;14 adapter/originality checks passed. See S2_SANDBOX_HANDOFF.md. No claim that the model generator matches the eight constructor examples; no deployment. Human review should focus on new design originality, not these failed drafts.

25 October checked-spec follow-up: user editorial feedback recorded without approval promotion. Two additional local math families and a bounded real-model specification-selection trial pass supported checks (14 rendered formulas). New preview: ignored checked-spec-trial-v1/questions.html. These are constructor-authored templates, not unrestricted model inventions; book mapping and human quality gates remain pending. See S2_SANDBOX_HANDOFF.md.

## S1b re-audit — 25 October

Full-identity F1 projection joins and weekly scope document/major/catalogue guards corrected.221 tests passed,1 skipped; new separate F1 projection:0 structural errors,106 holds. Effective policy remains0 eligible records/0 reviewed scopes;15 reserved document exclusions unchanged. Implementation re-audit complete; data acceptance and semantic holdout qualification remain pending. See S1B_HANDOFF.md for evidence and next handoff. No later-stage work, provider calls or deployment.

## Current-review projection — 25 October

Added Sol-owned review_policy_projection.py, project_authoring_reviews.py and
review_policy_projection_test.py. This read-only adapter consumes the existing
validated ReviewStore binding, resolves each reviewer's latest dimension decision,
holds stale/conflicting/malformed evidence and never creates an approval or edits
the effective retrieval policy. It does not authenticate arbitrary imported JSON;
its trusted caller is the local ReviewStore audit. Existing events are preserved.

Actual audit:40/40 math questions have current extraction passes,0 record errors;
curriculum/design review dimensions remain missing for40/40. These missing
approvals are distinct from already completed OCR work. Positive feedback on the
new question sets is recorded separately and does not approve source annotations.
Private immutable projection and aggregate status: authoring_work/review-policy-projection-v1.

Also held malformed policy lists/reviews and duplicate sidecar IDs before ranking.
Integrated review/projection/routing/F1/source/corpus/chat checks:246 passed,
1 skipped,7 existing FastAPI/Pydantic/SWIG deprecation warnings. No provider calls,
scans, embedding, quota resets, review writes, policy activation, VM work or push.

Prepared calibration.html plus a hash-named JSON under that private projection
folder: three source-bound summaries for source Maze Q1,Q21,Q35 (not the newly
constructed questions). Reviewer can confirm/correct book-topic mappings and the
necessary insight/route, or mark unknown. No repeat OCR review is requested.
This is a calibration sample; approving three examples cannot approve all40.
No difficulty buckets or scientific correctness are inferred from these labels.
The page is static/read-only and records no decisions; attribution and version-bound
integration are required after actual feedback. Broader holdout semantic qualification,
reviewed Maze scope and real-corpus retrieval benchmarks remain pending.

## Three calibrated summaries integrated — 25 October

The user confirmed the displayed topic and main-decision summaries for source
Q1,Q21,Q35. The confirmation is preserved, bound to the exact viewed JSON and
current question/catalogue/material hashes, in the ignored
calibrated-design-summaries-v1 directory. It does not approve complete routes,
all taxonomy labels, scientific correctness, the remaining37 items or publication.
Only route identifiers were displayed alongside the main-decision summaries;
full route bodies were not presented and are not marked reviewed.

Implemented calibrated_designs.py and audit_calibrated_summaries.py with tests.
The source schema's confirmed math_physics major is explicitly mapped to riazi;
unknown majors remain held. Current record and annotation revision/content,
document revision, evidence token and displayed topics must match. Existing
source/family exclusions still apply. The local audit returns only the reviewed
summary fields; no source literal, answer or full solution is emitted.

Actual local result:3 reviewed summaries,3 retrievable summaries,0 evidence holds.
Six saved local regressions pass: missing scope, changed evidence, excluded
sources, model attribution, changed summary and each individual curriculum scope.
Integrated suite:261 passed,1 skipped,7 existing dependency deprecation warnings.
An independent code review identified stale-annotation and family-exclusion
bypasses; both were fixed and covered by regression tests.

The effective production retrieval-policy file is unchanged and still has0
activated records/0 reviewed Maze scopes. The3 local summaries are a bounded
calibration library, not a release or full-corpus retrieval-quality claim.
No provider calls, scans, embeddings, quota resets, DB/pool writes, VM work or push.

Corrected the visible Q35 topic typo from کارتردها to کاربردها. The original
HTML was archived and a display-errata sidecar records both hashes; the frozen
catalogue and confirmed JSON were preserved to retain review bindings. A future
catalogue revision can incorporate the spelling correction with explicit migration.

Next technical handoff: use these exact scoped summaries in local authoring
experiments, with separately validated factual textbook grounding. Full source
eligibility, reviewed Maze scope and evaluator-only semantic holdout qualification
remain separate tasks. Do not request the same three confirmations again.

## Next-step checkpoint — 26 October

S2 three-brief local generation pilot is prepared, not accepted or complete.
Source receipt checks and four assistant-checked test-book image hashes are saved
privately. No live trial draft survived provider/network failures; these failures
are not question-quality measurements.53 focused offline tests pass.

Dependency now: user repairs the VPN/proxy's upstream TLS route, then Sol resumes
one fresh attempt and owns independent mathematical/option/novelty checks plus
rendering. Source/curriculum/holdout/release gates retain their existing separate
states. See README and S2_SANDBOX_HANDOFF for the exact resume boundary.

27 October update: the network dependency was resolved. Revised Gemini trial
produced3 checked questions; proof/metadata corrections and the geometry diagram
are versioned separately from raw drafts.65 focused tests pass. The current
dependency is scoped human editorial/novelty feedback on the new preview at
http://127.0.0.1:8773/questions.html. S2 remains experimental; production S2/S3
acceptance and release gates are not complete. See the latest README handoff.

27 October follow-up: the user accepted the3 displayed questions editorially.
Scoped feedback is saved. Independent answer-withheld solving matched3/3;
local replay/binding and regression-set freezing are implemented. The current
three-question review gate is fulfilled at that limited scope. S3 verification
prototype exists locally; production bank lifecycle and release acceptance remain
pending. Next Sol work is the larger predeclared benchmark and lifecycle failure
tests, not asking for the same editorial confirmation again.

Same continuation: the three designs now have a safe typed practice-spec bridge;
24 parameter cases are frozen and111 focused tests pass. This closes the small
local constructor/regression step, not the full production stage. No additional
API generation, bank activation or deployment was performed for those cases.

27 October next checkpoint: paired development benchmark protocol frozen
(20 pairs/40 planned items,0 generated). S3 local tests found completed results
being rescored after quarantine; result replay is now immutable for new attempts,
with conservative legacy recovery.128 lifecycle/API/recovery checks, TypeScript
and frontend build pass. New optional snapshot column is prepared in code and
tested on temporary databases; no server restart, VM migration or rollout.
See DEVELOPMENT_BENCHMARK.md. S3 remains partial; benchmark execution and expert
evaluation are next, followed by remaining release gates.

## Active checkpoint — 28 October2026

S2 paired experiment:32/40 final outcomes,21 drafts,8 untouched items;11 outcomes
are retained provider/protocol failures. Each of four configured Gemini generation
credentials reported terminal daily quota. Earliest retry approximately10:30
Tehran today. Generation is stopped, not automatically scheduled.

S3 local checks:21 exact keys matched assistant derivations/replays;18 blind-model
matches,3 provider-held.118 focused tests passed. A separately versioned editorial
presentation repairs3 diagrams and2 notation/option defects. No expert science,
curriculum-release or originality approval was inferred from these checks.

Human next: inspect the NEW sheet at http://127.0.0.1:8775/questions-ltr.html,
starting with R01,R16,R22; describe anything unnatural, routine or repetitive.
No OCR/old three-question review. Sol next after input and quota recovery: finish
the untouched8, consolidate paired results and revalidate prior blind evidence
before reuse. Production remains incomplete; deployment is not authorized.
See the latest README for saved evidence and the stale older resume file.

28 October afternoon update: all40 planned attempts are final, with24 saved
drafts/16 retained failure or format outcomes and0 pending. Quota was reset;
additional active project credentials were explicitly authorized and used without
changing provider/model/prompts. Gemini503 overload remained the generation issue.
All24 keys matched scoped local mathematical replay.18 existing blind matches
were revalidated and reused offline;6 drafts lack a blind-model comparison.
121 focused tests pass. The new24-question sheet and exact human editorial task
are in the latest README. Human review is pending, not implicitly approved by the
user asking who generated the questions. No source promotion or deployment.

## Current handoff — 30 October

The sample-style human gate now has positive qualitative feedback, conditional
on its actual narrow prompts. Geometry was specifically requested to use
parallel/similarity, and discrete tasks were modular. Broad coverage was not
evaluated. Do not re-request the same R16/R22 confirmation. No mathematical,
formal-tag or production approval is implied.

Next: Sol-owned follow-up preparation in FOLLOWUP_AUTHORING_V2.md: source-backed
mechanism diversity and explicit student solutions, separate from verification.
Original benchmark metrics stay frozen; no paired-arm winner can be inferred from
this unblinded overall feedback. Production S2/S3 and release gates remain open.

### Latest technical checkpoint — 30 October

- Original benchmark: 40 final attempts, 24 drafts; 23 replayed blind matches,
  zero disagreements, one retained access-denied verification (R06). The earlier
  18-match and six-uncompared statements are historical.
- New pedagogical geometry pilot: six final attempts, 2 structured drafts,
  2 provider errors, 2 protocol holds. Separate exact format projections make the
  latter two inspectable without relabeling them successful model outputs.
- Four keys independently checked, four answer-withheld matches. One diagram
  corrected; three absent diagrams remain not-applicable, not passes.
- Coverage reporting separates assigned mechanisms, proposed techniques and
  independently adjudicated mechanisms (the last remains null). No difficulty,
  student weakness, formal tag or originality approval is inferred.
- 131 focused tests pass. Frozen local review and evidence pointers live under
  ignored `backend/data/authoring_work/pedagogical-geometry-v2/`.

Sol next: finish the separately recorded two-item provider-recovery run, inspect
any returned outputs and freeze their checks separately. Preserve all original
failures and previous snapshots. Then request bounded editorial feedback on the
new mechanisms and whether their teaching explanations are clear; do not ask the
user to redo the original sample's overall style review. Expert scientific review,
source eligibility, final holdout evaluation and release remain distinct open gates.
No VM/push/activation is authorized by this continuation.

Recovery completion: the two extra attempts both drafted. All six mechanisms now
have assistant-checked keys; five have blind matches. Cyclic blind verification
failed at the provider's JSON generation (HTTP400), without a usable response.
The original six attempts still count 2 drafted / 2 provider errors / 2 format
holds. Two separate recovery drafts do not erase that failure rate.

The complete six-question snapshot is linked by private
`pedagogical-geometry-v2/combined-review-pointer.json`. It labels a false reflection
counterfactual and records the correction, incomplete alternate explanations,
three English structured pedagogies and diagram repairs. Original responses and
all review revisions are unchanged. Latest focused suite: 133 passed.

Human/editorial next: inspect G01–G06 in that NEW sheet for naturalness, meaningful
mechanism variety, repetition and clarity of the full teaching explanations. This
does not request another source-transcription review or imply expert approval.
Sol follow-up after feedback: a new explicit prompt revision for Persian teaching
adherence and checkable counterfactuals, plus systematic duplication/coverage
evaluation. Do not change the frozen prompts or bulk promote these questions.

### Additional offline work — language and copy screening

The owner asked to continue; useful technical preparation proceeded without
inventing new editorial approval. An additive draft policy module screens teaching
prose for Persian-script adherence. It flags 3/6 candidates; passing is explicitly
not Persian fluency or scientific approval. It leaves the v0.2 parser/prompts alone.
Six v0.3 prompt drafts now require Persian explanatory prose, complete alternate
proofs, feasibility sufficiency, recalculated counterfactuals and generic stem
figures. These prompts were not executed or promoted into production.

Offline scalar-normalized surface screening against the 24 previous generated
drafts plus the other five new items flagged zero close variants. Mathematical
isomorphism, shared reasoning chains and source-wide originality remain unresolved;
no held-out paper was read. New private reports are under `language-policy/` and
`originality-screen/` in the pedagogical pilot folder. The latest combined review
pointer now includes and binds those audits. No provider calls in this continuation.
Focused validation after the additions: 145 passed, including stale/unsafe audit
references and preservation of the frozen v0.2 prompt bytes.

## Owner review received — G01–G06

The owner has completed the requested editorial review. G01: too simple/direct
and its small segment/near-tangent appearance is poor. G03: familiar textbook
problem, at most a very easy exam item. G02/G04/G05/G06: positive Konkur-style
judgments; G05 also familiar. This closes the pending editorial task, with scoped
receipts stored privately against the exact combined review and candidates.
It does not establish expert correctness, formal tags or calibrated difficulty.

Sol next: use AUTHORING_DISTRACTORS_AND_SHORTCUTS.md to prepare a bounded new
design experiment: meaningful error-based distractors, option/guessing audits,
proof-backed fast routes and parameter-aware figure readability. No repeat human
review is required to begin this preparation. Preserve frozen pilot failures and
all review versions. Deployment and source promotion remain separate gates.

## Architecture follow-up after the editorial review

Read ARCHITECTURE_REVIEW_AND_CHANGE_CONTROL.md for confirmed legacy-upload and
vector-ownership findings, the adaptive phase-revision procedure and a read-only
Astra review prompt. Removed the timer-only fake upload card from Exams.tsx;
kept actual results and the backend APIs/data. VectorStore documentation now
describes shared-plus-private lookup correctly. No vector ownership migration,
data deletion, re-embedding or deployment was performed.

The shared-owner DEMO_USER_ID overload needs a separate caller/data audit and
tested explicit visibility/ownership design. Keep user filters meanwhile. Public
upload endpoints are registered even though current chat has no attachment
control; their deprecation is a scoped decision, not dead-code deletion by guess.

## Decision-pilot preparation completed

See DECISION_PILOT_HANDOFF.md. Three briefs are frozen with distractor hypotheses,
shortcut attacks and predeclared acceptance checks. Candidate format stays
compatible; the new model-output sidecars are proposals, never scientific review.
Implemented strict sidecar/envelope validation, projected short-segment screening,
and separate stem-only/option-aware evaluation packets with no key/solution leakage.

The first bounded invocation stopped at a credential-free ConnectError. No model
generation request was sent; 0 attempts / 3 pending. Current blocker is the VPN
HTTP proxy on10809. Resume only after connection change. Old trials, source data,
quota refusals and frozen reviews are preserved. No new human question review yet.
Focused verification: 175 passed. The local listener check found port10809 absent.
