# Local verification checkpoint — 27 October 2026

The user said “no the questions are good” about the exact three-question
review-v1 sheet. This is recorded as positive overall editorial/design feedback,
with the displayed HTML and presentation payload hashes. It does not assert a
qualified scientific review, corpus-wide originality, source-annotation approval
or permission to publish. The viewed pages remain unchanged.

## Completed local steps

- blind_trial.py projects only stems, ordered options and neutral aliases. It
  excludes proposed answers, solutions, design notes, source IDs and diagrams.
  This pilot is explicitly text-only; the stems specify the geometry completely.
- run_blind_authoring_trial.py checks current source/presentation/feedback hashes
  and makes a fresh independent Groq gpt-oss-120b request at high reasoning.
  Gemini authored the questions; Groq receives no answer-bearing material.
  Existing free-tier settings and saved credential blocks are respected.
- Actual blind result:3 solved answers matched,0 disagreements,0 unresolved.
  Request elapsed20.782 seconds. Final reported usage:1794 prompt,7719 completion,
  9513 total tokens. These are this response's reported values, not estimates.
- The blind explanation for geometry uses a slope expression that omits a
  vertical-side case. The answer remains4, supported by the existing general
  coordinate proof and an explicit vertical-side example recorded in the snapshot.
  Agreement alone does not certify every proof step.
- local_trial_snapshot.py and freeze_local_trial_validation.py combine bounded
  checks, the answer-withheld solver comparison and scoped editorial feedback.
  The mathematical/presentation replay runs before freezing: changing wording
  and rebasing editorial feedback cannot reuse stale mathematical evidence.
  Duplicate/missing records, stale keys and inconsistent match flags are held.
  Imported approval flags cannot grant release eligibility.

## Saved evidence

All real artifacts remain ignored under
backend/data/authoring_work/grounded-authoring-trial-v1/attempt-10/:

- review-v1/human-editorial-*.json and editorial-status.json;
- blind-solve-v1/ contains separate blind packet/local alias binding, original
  response, transport events, version-bound comparison and status;
- validation-bundle-v1/ contains immutable hash-named snapshots and status.

Current snapshot:3 questions,3 bounded check records,3 blind-answer matches,
3 positive editorial feedback records,3 ready for local development regression,
0 release-eligible. Earlier snapshots and all failed trial outputs are preserved.
The snapshot is a local evidence projection; its caller validates provenance.
It does not authenticate arbitrary externally supplied reviewer identities.

## Actual checks and remaining scope

Focused regression tests cover blind data isolation, malformed responses,
agreement/disagreement/uncertainty, stale evidence, duplicated coverage, revised
wording with old math checks, and attempted imported approval. Existing calibrated
retrieval, safe constructor, originality-screen and renderer tests remain in scope.
The current batch is a development regression set, not an unbiased quality estimate.

This is partial local S3 verification infrastructure. Application bank lifecycle,
concurrent claims, leases, quarantines and active-attempt/rating behavior have not
been changed or certified by this step. Production release still needs the
separate scientific/curriculum/novelty/evaluation gates and explicit rollout
authorization. No application DB, review ledger, pool, vectors or effective source
policy were changed. No VM work, deployment or push.

Next technical work: extend the same version-bound stages to a predeclared larger
development benchmark and the existing bank lifecycle, using synthetic failure
tests first. Keep subjective exam-likeness/expert judgments separate from model
agreement. Do not ask the user to approve these same three questions again.

## Checked specification bridge completed in this continuation

calibrated_families.py adds three bounded practice constructors to the existing
local model_spec_adapter: cubic real-existence counting, trapezoid parallel-line
offset, and modular power/square counting. Domains, answers, distinct distractors,
wording and geometry derive from declarative parameters before display. Unknown
parameters, executable fields, unsupported domains and edited proof/diagram
content are held. The output stays supported_practice_variant, never a claim of
a new design or an inherited human approval.

Independent tests solve the cubic-family quadratic directly, check geometry
under arbitrary horizontal shear including vertical-side cases, and compare the
periodic counter with exhaustive modular enumeration through5000. These are
bounded-family checks, not a solver for arbitrary model prose.

build_calibrated_spec_regression.py froze24 parameter cases (8 per family),
all passing canonical constructor checks, under ignored
authoring_work/calibrated-spec-regression-v1. It binds the source trial snapshot,
constructor/adapter code hashes and exact specifications. This is a regression
set of practice variants; it is not24 new creative questions or an unbiased
generation-quality benchmark. No API calls or production activation occurred.

Final focused integrated run:111 passed in8.23s,0 failed. Python compilation,
source evidence replay and snapshot freeze also passed. The current local
three-question editorial calibration is fulfilled; full S2/S3 and production
release remain open. Next integration work is the broader benchmark and existing
bank lifecycle. Expert scientific/curriculum/novelty judgments remain separate
release gates; this checkpoint does not manufacture those decisions.
