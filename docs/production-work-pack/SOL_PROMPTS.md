# GPT-6.1 Sol: core engineering and integration

Copy the startup prompt first. Then issue one stage prompt at a time. All stages
inherit [README.md](README.md), including local-only work and evidence gates.

## Startup prompt — S0

```text
You are the technical lead and sole integrator for Karzar/Boom in
C:\Users\Arsam\Desktop\Boom-merged. Read AGENTS.md and
docs/production-work-pack/README.md plus its required source documents.
Execute S0 only now; prepare later stages without starting them.

Inspect the dirty working tree, including untracked files, current source/import
formats, review gates, retrieval routing, question generation and pool selection.
Preserve all existing work. Confirm documented status from saved evidence; do
not trigger scans, embedding, paid calls, database migrations or provider probes.

Create docs/production-work-pack/TASK_BOARD.md and CONTRACTS.md. Define the
smallest contracts needed for separate question/answer PDFs, source classification,
review receipts, design records, generation specifications and eligibility.
Include source SHA, exam/session/booklet identity, printed question number,
page/crop references, content/image hashes, answer provenance, curriculum version,
inferred-vs-confirmed labels and independent review dimensions. Unknowns are null.
Distinguish schema versions from document/question revisions. Define immutable
IDs and correction/invalidation rules. Do not replace existing compatible formats.

List writable files for yourself and Freebuff, plus task dependencies. Freebuff
F0 leaves application code unchanged and can write its handoff immediately. Assign its new helper/test paths before
F1-F3. Specify how private artifacts are stored and referenced without secrets.
Publish small synthetic example records so Freebuff can work without live data.

Set an initial scoped pilot and a predeclared evaluation protocol with human
input still pending where necessary. List real gaps, not every hypothetical
improvement. Identify obsolete statements in old docs without bulk cleanup.

Deliver the board, contracts, exact F1 starting instruction, known blockers and
the README handoff. No push, VM work or production activation.
```

## S1 — Sources, question/answer pairing and retrieval roles

```text
Execute S1 using the S0 contracts and human H0-H1 source decisions. If any human
decision is absent, implement the schema and synthetic tests while holding the
affected real source. Integrate Freebuff F1 only after reviewing its patch.

Extend existing inventory/imports to link questions.pdf with answer-key.pdf and/or
worked-solutions.pdf by confirmed exam/session/booklet identity and printed
question number. Detect missing, repeated, conflicting and offset numbering,
multi-exam solution files, page continuations and ambiguous booklet variants.
Never zip questions and answers by array position or filename alone.

Keep source evidence, inferred design and scientific review independent. Preserve
originals and frozen snapshots; corrections produce versioned deltas. Bind answer
and transcription receipts to their source and content hashes.

Implement explicit retrieval purposes: authoring designs from eligible exam
examples; factual grounding from current textbooks; weekly plan scope from Maze
plus test-book ranges and student data. Apply role, major, curriculum and split
filters before ranking. Unknown sources and unreviewed candidates cannot become
trusted evidence through a broad fallback. Old exam topics cannot expand scope.

Freeze development and final-evaluation splits, including duplicate originals
inside compilations and close question-family variants. Protect holdout answers
from authoring prompts and blind solvers. Record retrieved IDs and filter reasons.
Test cross-role leakage, stale reviews, ambiguous answer joins and missing scope.
Return measured coverage and unresolved source mappings; do not bulk approve data.
```

## S2 — Design library and checked mathematical construction

```text
Execute S2 after eligible source records and representative human H2 reviews exist.
Build on question_design.py, exam_blueprint.py and current generation code.
Begin with a small set of reviewed math families; expand after demonstrable success.

Store assessed skills, necessary insight, representation, shortest valid solution,
essential assumptions, plausible misconceptions, distractor mechanisms and design
provenance. Inferred labels remain inferred until reviewed. Retrieve diverse designs
within the allowed curriculum rather than selecting only nearest wording.

Generate a structured problem specification before prose: domains, givens, units,
unknown, constraints, constructed parameters, solution evidence and optional figure.
Check existence and answer uniqueness before writing ordered options and Persian
wording. Use safe declarative specifications and allowlisted math operations; never
execute arbitrary model Python. Exact checks apply only to supported families;
unsupported/inconclusive cases remain pending.

Produce figures from the same specification as the mathematics. Validate labels,
scales, topology and stated assumptions. Separate reusable practice variants from
new reasoning designs. Test whether a purported hard design collapses to direct
substitution or an accidental shortcut. Extreme stays inside the current curriculum.

Preserve existing textbook citations, independent verification and retry behavior.
Add reproducible tests for contradictory quadrants, extraneous roots, empty domains,
equivalent options and figure/text disagreement. Save a small unpublished batch
with design/spec/source evidence for H3; do not claim creativity from prompt changes.
```

## S3 — Verification, bank lifecycle and reliable workers

```text
Execute S3. Extend existing question_quality, question_bank, pool and worker systems.
Integrate useful Freebuff F3 tests after independent review.

Separate a blind solve, exact supported checks, adversarial ambiguity/counterexample
review, and editorial/difficulty assessment. The blind solver must not receive the
draft answer or solution. Check final rendered wording and figures as well as the
underlying specification. Model agreement alone cannot create human review.

Keep correctness, requested difficulty fit, novelty and human review distinct.
A correct but basic item may be held for reclassification; a timeout is pending
verification, not corrupt mathematics. Every substantive correction invalidates
affected version-bound evidence. Preserve unaffected questions from failed booklets.

Implement eligibility as a server-side policy derived from evidence. Reporting a
question quarantines it according to the existing policy and stops future selection;
preserve attempts and define how active sessions/ratings are handled. Do not silently
rewrite an item already served to students.

Workers need durable stage checkpoints, idempotent completion, bounded retries,
stale-lease recovery, graceful stop and distinct wait reasons. Preserve per-key/model
quota state, actual retry deadlines and successful results. No assumption that keys
share capacity without evidence. Measure calls/tokens per accepted question using
available usage data; distinguish missing usage from zero.

Use temporary databases and injected transport/provider failures to test restart,
concurrent claims, partial saves, access denial, daily quota, 503 and malformed data.
Return an eligibility matrix and specific failure evidence, not just a passing count.
```

## S4 — Local evaluation and student experience

```text
Execute S4 after S1-S3 and H3 reviews. Keep the final holdout sealed until the
predeclared candidate is frozen. Tune on development only. Report all exclusions.

Compare current generation with design-conditioned construction using the same
curriculum/task mix and bounded budgets. Include easy, Konkur, hard and extreme,
figures, and every subject claimed as supported. Measure correctness, ambiguity,
unique answer, curriculum fidelity, originality, shortest-solution difficulty and
teacher-rated exam likeness. Report numerator/denominator, disagreements and limits.
Evaluate retrieval across subjects before changing dense/hybrid/reranker policy.
Never select a production winner from the existing six-query pilot alone.

Integrate the reviewed bank into practice, full mocks and Colosseum. Preserve the
current full-paper count configuration, 10-question weekly Maze mode, and disclosed
previous-scope fallback. Insufficient coverage must not silently change the requested
exam or serve unchecked items. Track version-level exposure and prefer items unseen
by both ranked players. Hide answers/solutions until the appropriate server-side state.

Implement clear loading, empty, retry and provider-wait states. Keep request latency
independent of background generation. Respect protected planner blocks, book test
ranges, homework synchronization and account isolation during integration.

Before Freebuff F5, supply an integrated isolated test harness with admin and
non-admin identities, review routes, representative pool fixtures and controlled
provider responses. The existing ui_fixture_server.py is a starting point; its
ordinary accounts and stubbed generation do not exercise all requested workflows.
Declare which routes/scenarios are implemented in the harness so missing fixtures
are not mistaken for product defects. Never point it at the real student database.

Support H4 with first-attempt/exposure/assignment records, minimal participant IDs,
and conservative difficulty estimates. No precise ability or discrimination claims
from 20 users. Run targeted backend/frontend tests and actual local browser workflows.
Return a pilot report and remaining release blockers.
```

## S5 — Prepare and, when explicitly authorized, deploy

```text
Prepare S5 after the scoped pilot is accepted. This prompt first authorizes LOCAL
release preparation. The existing AGENTS.md corpus restriction requires the user's
explicit later instruction before push, VM access, transfer or activation.

Review all intended changes and Freebuff contributions; preserve unrelated dirty
work. Run appropriate integrated backend tests, frontend tests, TypeScript/build,
dependency checks and secret/artifact checks. Historical pass counts are not current
results. Test auth/account isolation, admin authorization, answer-key secrecy,
reports/quarantine, duplicate claims, interrupted sessions, scope fallback and backups.

Build a versioned release manifest containing code revision, eligible corpus IDs,
content/image checksums, embedding provider/model/dimensions, schema and prompt
versions, evaluation reports, limitations and rollback instructions. Export only
eligible shared resources. Never replace the application account database with the
laptop database. Keep raw PDFs, credentials, local scanner state and rejected data
out of Git and frontend bundles.

Prepare a target-capacity test for the 2GB VM: memory, startup, concurrency, storage
and latencies under the intended pilot load. Keep OCR/heavy background work local.
Document a verified reserve policy and honest behavior when stock/provider capacity
runs out. Do not promise uptime from free-tier keys alone.

Present the exact candidate and remaining decisions for H5. After explicit deployment
authorization, fetch first, preserve remote work, use fast-forward only, back up SQLite
through its backup API and Chroma with writers stopped, preserve JWT secrets/accounts/
private uploads, install compatible dependencies, import verified shared data and
deploy the same revision. Never copy a laptop localhost proxy to the VM.

Verify the public frontend revision, API and authenticated workflows, not health200
alone. Exercise rollback if verification fails. Send no OTP to an unapproved recipient.
Record deployed revision, corpus version, checks and unresolved limitations.
```
