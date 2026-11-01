# Claude comparison handoff — 25 October 2026

Status: requested comparison completed locally; targeted human calibration remains.
The original supplied report and frozen pass-A records are preserved unchanged.
No provider calls, new scans, embeddings, human receipt writes, activation, push,
deployment or VM work occurred in this comparison task.

Private report: backend/data/authoring_work/reasoning-comparison-v1/COMPARISON_REPORT.md
Private status.json points to the imported report SHA and frozen baseline manifest.
Raw external sections are stored under their report SHA. The attached report covers
40 math items; the frozen Codex annotation pilot covers14. Only14 therefore support
a direct baseline comparison;26 are reviewed as external analyses without claiming
a pre-existing independent Codex baseline.

Measured evidence:
-40 external printed keys align with40 corresponding recorded publisher keys.
-14 shared proposed final answers agree. This is not a scientific accuracy score.
-Manual route comparison finds the same core route in13 shared cases; question21
 uses different valid methods. This is descriptive comparison, not normalized tag
 agreement or a statistical model ranking.
-Eight bounded computations/domain checks reproduced in ignored reproduce_checks.py;
 results in reproduced-checks.json. Original claimed Claude code was not supplied.
-27 comparison/pilot/taxonomy synthetic tests passed. Import tests cover numbering
 rather than row-position alignment, duplicates, malformed keys, stale baseline,
 non-development splits, incomplete scope, no inferred taxonomy mapping and no promotion.
-External model version, prompt, PDF byte SHA and procedural independence remain
 unverified. Publisher-answer access means this is not a blind-solver evaluation.

Evaluation conclusion: Claude's solution descriptions and alternatives are richer
and some primary descriptions are more specific than the existing generic tags.
Codex's source/revision/catalogue contracts remain useful for safe machine ingestion.
Retain both originals; use explicit candidate reconciliation after human decisions.
The report identifies two correctable external presentation/explanation issues,
broad labels in passA, unproven shortest-route claims and speculative distractors.
No wholesale taxonomy change or approval was made.

Human decisions are narrowed to:
1. Granularity of algebraic restructuring, independent product counting and the
 distinction between requested limit evaluation and a limiting-case heuristic.
2. Closed-interval endpoint convention for question15; preserve the published key
 under its intended convention and make generated wording explicit.
3. Book-backed default methods versus optional valid methods whose curriculum
 inclusion has not been established. Use the publisher's school-level route by default.

See the private report for all40 per-item notes, the14 direct comparisons and
specific recommendations. No new files or complete re-solving are requested from
user. Existing source-text approvals are not converted into reasoning-tag approval.
