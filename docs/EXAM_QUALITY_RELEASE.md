# Exam OCR quality and release workflow

This work is local. No candidate index or evaluation automatically activates in production.

## Evidence layers

The batch snapshot contains 4824 valid question pages and 17605 question records.
It preserves OCR candidates, not approved answers or reviewed textbook facts.
Stable identities are document SHA256, PDF page and question number. Content hashes
bind reviews and vectors to the exact revision. Originals and earlier snapshots remain intact.

## Implemented controls

- Ordinary text chunking uses paragraph and sentence boundaries, protects common
  abbreviations and delimited math, keeps whole-unit overlap, and enforces size limits.
  An oversized atomic equation is rejected explicitly rather than silently cut.
- Question records remain complete parents. Bounded linked child chunks can be
  retrieved while the original parent is retained for reading and review.
- Automatic audit flags missing major, repeated options, suspicious delimiters,
  exact duplicate content, diagram dependence and possible continuations.
  Flags are suspected issues. No flags is not evidence of accuracy.
- Curriculum suggestions can only reference existing book-backed catalogue nodes.
  Suggestions are explicitly unverified and never expand permitted lesson scope.
- Continuation proposals never automatically join text. A join requires adjacent
  pages in one source and explicit review matching every part hash and source image.
- Incremental delta records added, unchanged, removed and superseded content.
  Snapshot checksum/model/dimensions/content checks prevent accidental vector reuse.
- The embedding launcher has a per-snapshot OS writer lock. Resume reuses compatible
  vectors. Actual minute limits wait; daily/access failures do not retry in a tight loop.
- Release exporter requires matching source/content hashes, verified curriculum IDs,
  scientific verification evidence, answer, matching finite vectors and passed evaluation.
  Missing gates hold the record. Scientific model agreement alone is insufficient.

## Commands from backend

```powershell
.venv/Scripts/python.exe -X utf8 scripts/stage_exam_embeddings.py --workers 4
.venv/Scripts/python.exe -X utf8 scripts/audit_exam_snapshot.py
.venv/Scripts/python.exe -X utf8 scripts/evaluate_exam_retrieval.py
.venv/Scripts/python.exe -X utf8 scripts/evaluate_exam_generation.py
```

Results are private under data/exam_staging/batch-5000-v1. The local monitor has
/corpus-quality plus source comparisons in /corpus-item. It exposes no approval
button and makes no claims of teacher review.

## Measured baseline and limits

The initial retrieval pilot has six manually written queries for three checked
math questions, against a partial 3843-question evaluation corpus. Three gold
vectors were added only to memory, clearly recorded as an overlay.
Dense Recall@5 was 1.0, BM25 0.3333, RRF hybrid 0.6667, and reranked 0.3333.
This small pilot found a reranker regression. It does not justify production tuning
or a claim about all subjects. Physics, chemistry, diagrams, other grades and held-out
source documents still require a representative source-checked benchmark.

The first local math draft hit provider HTTP503 during verification. A subsequent
strictly textbook-grounded draft passed the existing independent verifier; it remains
unpublished and difficulty is not calibrated. One successful example is not a
representative generation benchmark. Candidate OCR was not promoted into trusted
textbook evidence.

quality-history.jsonl records audit coverage and detection counts. These are not
accuracy scores. retrieval-pilot.json records measured rankings and limitations.
No VM upload, push, bulk approval or live collection switch is authorized by this workflow.

## 22 October continuation

The frozen batch completed all 17,605 vectors. Subsequent scans do not mutate it.
Evaluation now validates collection model, dimensions and snapshot identity, rejects
nonfinite/zero vectors, preserves timestamped reports, and caches query embeddings
by exact text, embedding model, dimensions and query/document task. The cache is
private ignored data; it contains no credentials. No retrieval policy is automatically
selected from the small pilot.

Release still requires source-bound review, calibrated difficulty, novelty review,
book-backed curriculum, and scientific evidence. Initial project acceptance policy
requires at least 20 source questions from three held-out documents covering math,
physics and chemistry, 30 queries, Recall@5 >=0.9, MRR >=0.8, and 20 verified
generation examples. These thresholds are project policy, not universal guarantees.

Latest checks: backend regression 997 passed / 3 skipped; subsequent focused
cache/readiness/quality checks 18 passed. Full-snapshot retrieval rerun was blocked
before producing metrics: 12 saved daily-quota refusals and one network/provider
embedding failure. No new retrieval accuracy claim is supported. Existing partial
pilot metrics are retained; retrieval-run-status.json exposes the blocked run
separately. Retry after connectivity/provider recovery; do not clear actual daily
refusals or re-embed completed source vectors.

## Successful full-snapshot retrieval retry (22 October)

After the proxy recovered, the six-query math pilot completed against all 17,605
stored vectors, with zero overlay vectors. Recall@5 / MRR: BM25 .3333 / .0833;
dense 1.0 / 1.0; RRF hybrid .6667 / .3333; reranked .3333 / .2083.
This confirms the earlier fusion/reranker regression on this limited benchmark,
not universal dense superiority. Three source questions and math-only coverage
are insufficient for release. No production policy or collection was changed.

## Authoring difficulty checks (22 October)

Source grounding no longer instructs copying textbook numbers. A separate
level-specific authoring contract rejects arithmetic length as a substitute for
conceptual difficulty. The contract follows source/style excerpts so examples do
not override the requested design. New drafts carry their requested tier through
verification and repair. The independent correctness audit additionally reviews
the shortest solution, direct-substitution shortcuts, interacting concepts and
necessary insight. Missing difficulty evidence defers the question; a specific
tier mismatch holds it with difficulty_below_requested_tier, separate from
content_valid. This remains a model estimate, not student-calibrated difficulty.

The original extreme trigonometry example was independently audited again:
scientifically correct, but explicitly rejected for the extreme tier because
it only substitutes into identities and contains no essential insight. Evidence
is saved privately as sample-original-difficulty-audit.json. Generation/queue/API
regression checks: 75 passed. This does not prove future questions are creative;
new outputs still require inspection. Nothing was deployed or approved in bulk.

The follow-up v3 extreme draft changed to reverse reasoning but still has
inconsistent quadrant constraints. Its computed beta is below pi/2 despite
requiring quadrant II. The assistant's explicit derivation is retained separately
in sample-extreme-design-v3.json; no human review is claimed. The independent
provider also returned HTTP503, so this draft remains unverified and unpublished.
Prompt changes and difficulty gates are implemented, but generation quality is
not yet demonstrated acceptable for the extreme tier.
