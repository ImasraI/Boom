# Next quality experiment — development protocol v1

Prepared27 October2026, before generating the experiment's questions. This is a
math-only development comparison, not final holdout evaluation or production
acceptance. The three previously displayed questions are calibration examples
and are excluded from the new evaluation output set.

## Frozen design

20 paired task specifications:7 algebra/cubic-identity tasks,7 parallel/similarity
geometry tasks and6 modular-reasoning tasks. Each has2 arms, for40 planned items:

- Baseline: generic task requirements and factual mathematics.
- Design-conditioned: the same inputs plus approved-summary-derived generic
  reasoning guidance. No raw source exam questions or answer keys are sent.

Use the same configured free-tier model, factual scope, reasoning settings,
output budget and retry policy in both arms. Freeze the actual provider/model
assignment before the first request. Ten pairs have baseline first, ten have
conditioned first, in a seeded randomized order. Never feed one arm's output into
the other arm's prompt or silently replace a failed item with a successful one.

These are free-form authoring tasks; the24 checked template variants remain a
separate regression set. The comparison can measure the effect of this narrow
design guidance, not the benefit of the entire RAG stack. Reserved exam papers
remain excluded. Historical difficulty fields are not assigned by this protocol.

## Checks and measurements

Count attempted specifications, provider refusals, malformed outputs, usable
drafts, mathematical failures and editorial holds separately. Independently
check existence, domains, a unique correct option, figure/text consistency and
scope. Keep raw output, corrections, prompt/content hashes and actual reported
usage. Missing usage is unknown, not zero.

Reviewers see neutral aliases and randomized presentation, not arm/provider
labels. Blind solvers receive no proposed keys, solutions or design explanations.
Human ratings cover clarity, Konkur likeness and structural departure separately
from correctness. Draft quality anchors:1 unusable/misleading;3 usable but routine
or requiring edits;5 clear, insightful and naturally exam-like. The rubric awaits
expert calibration; these scores are not student difficulty estimates.

No unresolved critical mathematical defect is acceptable in a released item.
Model agreement and positive editorial feedback do not manufacture scientific,
curriculum or corpus-wide originality approvals. The sample cannot establish
global generation quality or qualify a105-question full mock.

## Preparation checkpoint — 27 October

The hash-named real manifest and status are ignored under
backend/data/authoring_work/development-benchmark-v1. Preparation has produced
20 paired specifications,0 generated items and0 provider calls. Rerunning
prepare_authoring_benchmark.py preserves the frozen protocol/progress; changed
inputs require a new revision. Do not reset its counters to restart an experiment.

Sol's next execution work is a bounded paired runner with durable checkpoints
and review export. Subsequent expert review applies to the NEW batch; no repeat
approval of the existing three-question sheet is requested. No activation, push
or deployment is authorized by this protocol.

## Bank-lifecycle issue fixed alongside preparation

Completed mock submissions previously rescored their results against the current
active question bank on retry. Reporting an incorrect question after submission
could change the returned score from33.3% to100%, while history kept33.3%.
Retiring all questions could make the completed result return409.

New local code stores a nullable result_snapshot on MockAttempt with the original
scoring response and review, committed with the attempt. Authorization and the
per-user database write lock run before replay. Later reporting/restoration does
not change that completed result or create another attempt/weakness observation.
Quarantine still excludes questions from future selections.

Legacy attempts preserve stored scores/counts. A full immutable-booklet review
is reconstructed only when it agrees with those counts. If an old scored subset
cannot be recovered, the response retains totals and marks the detailed review
incomplete; the UI explains the missing detail. It does not invent a question-level
or per-subject breakdown. Snapshot data inconsistent with stored metrics falls
back to that legacy handling.

The nullable column is added through the existing ensure_schema mechanism on
application startup. Compatibility was tested on a temporary legacy SQLite file
and retained its old attempt. No manual migration or VM operation was performed.
This code has not been deployed. Existing live local servers were not restarted.

Validation:128 focused lifecycle/API/challenge/queue/recovery tests passed,
including8 new historical-result regressions. Real HTTP transports were blocked
during the run;0 outbound attempts occurred. TypeScript and the frontend build
passed. Existing dependency/datetime deprecation warnings remain. These checks
do not certify every worker or every deployment path.

## Execution checkpoint — 28 October

The actual saved state supersedes the earlier zero counts:21 drafts,2 protocol
holds,5 provider errors,4 daily refusals and8 untouched items out of40 planned.
There are8 complete draft pairs. The comparison remains incomplete.

All21 exact keys matched scoped assistant mathematical replay;18 also matched
answer-withheld model solving, with3 provider-held. Raw versus repaired quality
is explicitly separated:3 diagram corrections and2 notation/option repairs live
in a new editorial presentation, while every original outcome is preserved.
Human Konkur-likeness/novelty calibration is pending. No global accuracy or arm
superiority claim is justified.118 focused tests pass; no production activation.
The latest README contains the current review URL and exact continuation boundary.

Afternoon continuation:40/40 attempted outcomes are now final (24 drafts,
2 protocol holds,10 provider errors,4 daily refusals). Nothing was substituted
for failed attempts. All24 exact keys matched bounded assistant replay;18 prior
blind comparisons were revalidated offline and carried only for unchanged raw
questions. Six remain without blind-model comparison.121 focused tests passed.
Human editorial ratings are still pending. The saved count of usable drafts is
not40, and neither raw outcome totals nor repaired presentation quality imply
expert review, novelty, arm superiority or production readiness.
