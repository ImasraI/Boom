# S1b local handoff — 23 October 2026

Implemented: source-specific routing and conservative split enforcement. Not a production activation, scientific approval or demonstrated retrieval-quality improvement.

## Actual changes

- source_routing.py defines explicit authoring_design, factual_grounding, weekly_scope and weekly_tests purposes. Filters execute before ranking: confirmed source role, explicit development document/record/family membership, major, current catalogue revision and existing knowledge nodes, exact content/image/revision-bound extraction/curriculum receipts, design evidence for style examples, unresolved issues, and reviewed scope/test ranges. Unknown input is held. Decisions report filtered IDs/reasons and retrieved IDs without source text.
- HybridSearch.search gains an optional purpose/context route. It intersects approved chunk IDs with user/shared ownership at collection.get before lexical/vector scoring. Store document identity and exact text hash must match sidecars. Legacy general search remains available for unrelated existing callers; factual text chat/streaming, mock book grounding and weekly test selection now opt into strict purposes.
- exam_style references require reviewed sidecars and current split exclusions before topic ranking. Exact/number-only copy detection remains an offline boolean comparison against qualified source rows; held content is not returned as prompt examples.
- Weekly planner scope now requires a unique reviewed applicable Maze row, with curriculum/source attribution. Missing/overlapping scope returns no trusted context. Legacy extractor is retained under an explicitly candidate-only helper for review, not used as a trusted fallback. Weekly test retrieval no longer substitutes unrelated chunks when topic matching fails.
- freeze_authoring_split.py binds H1 catalogue SHA and produces versioned immutable split archives plus an effective exclusion sidecar. Does not change PDFs, original snapshot or vectors. New code reads excluded source IDs regardless of duplicate filenames.
- preflight_authoring_packet.py integrates accepted Freebuff F1 as a read-only subprocess on an explicit projection of S1a sidecars. Original packets stay intact. Classification evidence list is explicitly rendered into F1's string contract; mapping states remain unresolved. F1-owned implementation was not edited.

## Measured local evidence

Private backend/data/authoring_work/h1/split-audit-v1.json:15 reserved PDFs (five older combined exams plus10 new separate files);1,008 frozen records from older reserved documents;992 number-masked template groups excluded,1,001 IDs in those groups (short unmatched records still excluded by document ID). Exact/number-masked matches are only duplicate signals; semantic family uniqueness across new PDFs remains unknown. Deny-by-default development admission prevents those unknown records from leaking meanwhile.

Seven saved experiment artifacts inspected offline for reference IDs; retrieval-pilot.json contains12 references from older reserved exams. Those referenced cases are development-exposed, not clean final holdouts. Other old cases have unknown exposure. Do not claim the five old PDFs are unseen. New10 remain reserved final-evaluation candidates; no question/answer text from those PDFs was fed to a model. Cover-only identity probing found no reliable native date; individual year/session pairing beyond user-confirmed fifth pair remains unresolved. A controlled evaluator can qualify them later without supplying their contents to development.

Private effective policy retrieval-policy-v1.json contains0 eligible source records and0 reviewed Maze scope rows. This is deliberate: user curriculum approval is not a transcription/design/source receipt, and no matching review evidence was fabricated. Therefore strict local routing currently returns empty/held rather than unreviewed examples. No quality or speed improvement is claimed. Content reviews and representative benchmarking remain required before this routing is useful for generation or deployment.

F1 projection preflight:exit0,0 structural errors,106 evidence holds (105 question/answer records plus unresolved pairing). Report: authoring_work/s1a-mapped/f1-preflight/report.json. Missing source/science review is preserved.

## Actual checks

- New routing + source/F1 tests:60 passed before later extra range check.
- Integrated corpus/planner/pool/trace/F1/routing regression:284 passed,1 skipped,15 dependency/date warnings.
- Final chat-vision/routing checks:14 passed.
- Final routing/corpus rerun after audit-trace and node/range guards:156 passed,1 skipped; compile checks passed.
- Earlier strict-filter change caught4 regressions. Two positive style fixtures were updated with explicit synthetic policy receipts. Offline copy detection was corrected to remain effective for held examples; all four now pass.
- git diff --check passed, with an existing unrelated line-ending warning.
- No provider request, OCR worker start, embedding, database migration, live corpus switch, VM change, commit or push in this step.

## Contract and next steps

H1 user scope decisions and operational exclusions are frozen. Final scientific/semantic suitability and unseen-evaluation qualification remain held. Treat them as explicit evidence gates, not requests for the user to manually compare all papers. This step does not magically certify holdouts.

Next SR: authorized review receipts, real source adapter, server-side authorization/binding and controlled evaluator access. Populate eligible sidecars only from accepted receipts. H2 will receive a small clear visual/scientific review packet once SR is ready. Freebuff F3 still waits for H2. Do not lower these gates because current eligible count is zero.

Important remaining limitations: scoped ranking currently uses local cosine+token-overlap scoring on the prefiltered corpus and has not been benchmarked against the original RRF/reranker policy; representative evaluation must precede activation. Question-bank textual retrieval now uses the factual purpose filter; image retrieval additionally requires reviewed image sidecars before embedding/ranking, and loaded bytes must match the bound image SHA. OCR-image fallback requires explicit reviewed image IDs. End-to-end real multimodal evaluation remains pending. Split guards apply to strict purpose-enabled routes; this is not a global Chroma access-control replacement. Review policy manifests must be supplied by trusted local/server integration, not client payloads.

## Completion boundary

S1b implementation is locally reviewable and tests pass. Full task acceptance remains conditional: semantic family/compilation qualification for new PDFs and real-corpus multimodal evaluation remain pending. Keep the roadmap task in progress rather than treating this handoff as final release evidence. No additional files are requested from the user; these are technical/reviewer follow-ups.

Final isolation hardening: question-bank textual lookup now opts into the same source purpose; image retrieval admits only reviewed image-sidecar IDs before ranking. OCR-image fallback also requires explicit reviewed IDs. Actual image bytes are checked against bound SHA256 before vision input. The final combined regression run passed293 tests,1 skipped,15 existing dependency/date warnings. Missing image hashes are rejected; positive legacy image fixtures now supply explicit synthetic hashes. The previous note about unmigrated channels is superseded. Final holdout semantic-family qualification and source receipts still remain held; this does not certify end-to-end release readiness.

## S1b re-audit — 25 October 2026

Scoped local implementation re-audit completed; this is not source approval or
release readiness. Later S2 sandbox work is preserved and was not advanced here.

Two reproduced defects were fixed:
1. preflight_authoring_packet.py previously collapsed answers into a dictionary
   keyed only by printed number. It now requires a unique full identity match
   (exam, session, booklet, section, printed number) and a unique question identity.
   Missing/duplicate/conflicting identities produce no answer provenance. The
   H0-specific combined-document projection remains a held projection, not a
   generic final association approval. Existing S1a source-pairing records are intact.
2. reviewed_week_scope previously trusted a reviewed row without checking source
   document exclusions/development admission. Weekly scope and test retrieval now
   also enforce source-document admission, major and curriculum scope binding.
   A stale reviewed flag cannot override a reserved/excluded schedule document.

Changed Sol-owned paths: backend/scripts/preflight_authoring_packet.py,
backend/app/rag/source_routing.py, tests/source_routing_test.py,
tests/preflight_pairing_test.py and these handoffs. Freebuff-owned validator,
original PDFs, frozen split archives, old F1 checkpoint, review ledger, vector
stores and credential quota state are unchanged.

Evidence:68 focused routing/F1/pairing tests passed. Integrated routing/F1/source/
corpus/chat-vision run:221 passed,1 skipped,5 existing SWIG warnings (19.00s).
New cases exercise same-number/different-session joins, duplicate questions and
answers, missing booklet identity, excluded reviewed schedules and cross-major/
catalogue weekly scopes. No model requests, scanning, embeddings or DB migrations.

Fresh private aggregate evidence:
backend/data/authoring_work/s1b-audit-20261025/audit.json and projection/f1-preflight/report.json.
The new derived projection was written separately, preserving the old checkpoint.
105 questions/105 answers,105 unique full-identity candidate joins; F1 exit0,
0 structural errors,106 holds. Candidate joins are not reviewed associations.
Policy catalogue SHA matches the current catalogue.15 document exclusions,
1,001 record exclusions and992 number-masked family exclusions remain in effect.
All four purposes have0 eligible records;0 reviewed Maze scopes remain present.
No corpus quality/coverage improvement or successful trusted retrieval is claimed.

F1's bounded offline validator acceptance is supported again by the actual
48-test validator suite inside the integrated run. FREEBUFF_HANDOFF.md's older
'not accepted pending Sol review' statement is obsolete; its ownership and
scientific limitations still apply. Do not bulk rewrite historical docs.

Remaining acceptance gates: current role/revision-bound source receipts and
reviewed Maze scope need a trusted adapter into the effective policy; existing
human editorial feedback is not automatically such a receipt. Semantic overlap
of new evaluation candidates and old compilation family variants remains
unqualified. Old reserved exams have recorded development exposure; no clean
unseen holdout claim is warranted. Scoped ranking and multimodal real-corpus
quality remain unbenchmarked. Existing document-level deny-by-default holds stay.

Next handoff: controlled review/policy integration and evaluator-only split
qualification, not more source uploads or blanket approvals. No deployment,
production activation, push or VM work is authorized or performed by this step.

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
