# Freebuff: bounded implementation and independent QA

Use one chunk at a time, within the daily allowance. All chunks inherit
[README.md](README.md). Sol owns integration and shared contracts.

## Startup prompt — F0

```text
Work in C:\Users\Arsam\Desktop\Boom-merged. Read AGENTS.md and
docs/production-work-pack/README.md. You are the bounded tooling/QA worker.
Execute F0 now, without changing application code or starting provider jobs.

Inspect existing inventory/import, quality viewer, tests and documentation. Read
git status and preserve every existing change. Do not read or print private keys.
List what already works, concrete gaps, and candidate new files you can own without
colliding with Sol. Focus on question/answer PDF associations, evidence display,
failure recovery and reviewer usability. Distinguish saved historical results from
current observations. Do not treat a README checklist as verified implementation.

Write only docs/production-work-pack/FREEBUFF_HANDOFF.md with your findings,
proposed F1-F3 files, commands actually run and exact next step. Do not modify the
shared TASK_BOARD or contracts. If Sol's contracts are not ready, report that
dependency and prepare synthetic test scenarios; do not invent incompatible APIs.
```

## F1 — Offline source/review input validator

```text
Execute F1 after Sol has published CONTRACTS.md and assigned your files.
Suggested ownership: backend/scripts/validate_exam_review_inputs.py and
tests/exam_review_inputs_test.py. These are proposed new files; confirm they are
unclaimed before editing. Use the existing exam_corpus helpers where appropriate.

Implement a read-only CLI accepting explicit inventory, manifest and receipt paths.
Check source identity, page/question references, question/answer pairing metadata,
duplicate aliases, missing images, content/image hash mismatch and incompatible
schema versions. Flag ambiguous numbering and unknown classifications. Emit an
actionable report with IDs, reasons and source locations. Never repair/approve
records, overwrite snapshots, load credentials, call providers or import Chroma.

Use synthetic temporary files to test missing and conflicting answers, repeated
question numbers across booklets, split solutions, stale receipts, path traversal,
missing images and a valid pair. Respect the distinction between structural validity
and scientific correctness. Avoid rereading the whole corpus on every UI refresh.

Run the specific tests through repository pytest so tests/conftest.py isolates data.
Update your handoff with invocation examples, actual results and integration notes.
Sol reviews and wires this tool; do not modify its core modules.
```

## F2 — Source and question review screen

```text
Execute F2 after the review contract is stable. Sol must assign a new standalone
view/component and synthetic fixture/test files. The current local corpus viewer
is Python-generated HTML in exam_quality_view.py, separate from React RagInspector;
do not assume they are one UI or edit their routing concurrently.

Build a review screen using the assigned contract and synthetic data first. Show
original page/crop beside Persian transcription, ordered options, figure, answer
source, curriculum tags and separate evidence states. Include missing images,
continuations, uncertain symbols, stale receipts, disagreement and zero eligible
records. Clearly identify inferred labels and model-only judgments.

Support RTL, readable mathematics, keyboard navigation, zoom and narrow screens.
Escape source/model text; never inject raw HTML or execute model content. Bind
image requests to approved source IDs rather than arbitrary file paths. Preserve
the existing visual style and accessibility. Do not add click animations or removed
streak/lifestyle/AI-customization panels.

Implement human decision entry only against Sol's provided API/contract. A button
must not approve all records, impersonate an expert, or bypass hash/version checks.
If that API is absent, deliver a read-only preview with an explicit dependency.

Deliver screenshots using synthetic data, actual checks, and a small integration
patch proposal. Sol performs monitor/router wiring and authorization enforcement.
```

## F3 — Independent adversarial and recovery fixtures

```text
Execute F3 in a new Sol-assigned test module. Inspect existing suites first and
cover missing behavior, not duplicated assertions or implementation details.

Construct minimal synthetic cases for contradictory quadrant/domain constraints,
equivalent options, incorrect option reordering, wrong answer-PDF joins, graph/text
disagreement, obsolete curriculum tags and copied question structures. Include a
correct but too-easy question and a valid difficult one with explicit expected
evidence. Have Sol or a human check mathematical fixture truth before relying on it.

Test that stale source hashes invalidate approvals, interrupted requests preserve
completed stages, provider errors do not mark questions corrupt, terminal daily
quotas are respected, independent keys remain independent, and duplicate worker
claims cannot publish twice. Use temporary storage and stubbed transports; never
disconnect the user's VPN or mutate real quota/checkpoint files.

For each failing case, return a minimal reproduction, expected behavior and actual
behavior. Fix only your assigned helper/fixture files. Report core defects to Sol
with file/function references. Do not relax assertions or eligibility to get green.
```

## F4 — Candidate design annotations

```text
Execute F4 only on the small development batch assigned by Sol, never final holdouts.
Use existing authorized free tools within limits; do not launch unbounded API work.

For each eligible source question, propose curriculum-backed skills, necessary
insight, representation changes, shortest checkable solution, distractor mechanisms
and what makes the item demanding. Cite exact source/question IDs and retain unknowns.
Flag OCR uncertainty before interpreting a formula. Do not infer an author's private
thoughts or invent a source solution. Distinguish your solution from the printed key.

Suggest one practice variation and one substantively different reasoning design.
Explain the difference beyond changed numbers. Save candidate annotations under
ignored backend/data/authoring_work/ using the contract, marked model-inferred and
human_reviewed=false. Include model label, input revision and concise checkable
evidence; do not store hidden reasoning or secrets.

Stop at the assigned batch size. Send disagreements and proposed designs to human
H2-H3 and Sol. Your output is review material and cannot promote the question bank.
```

## F5 — End-to-end QA and operator handoff

```text
Execute F5 against Sol's integrated local candidate and synthetic test accounts.
Use the supplied fixture server/temporary database; never reuse a real student's
account for destructive testing. Do not access production without explicit scope.
First verify S4 supplied admin/non-admin identities and the review/pool routes.
The older ui_fixture_server.py alone lacks some of these. Report missing harness
coverage as a dependency; do not switch to real services to complete the checklist.

Exercise login, separate-account planning, mock selection, shortage behavior,
ranked current/previous Maze scope, question images, answer hiding before submission,
report/quarantine, admin permissions and review workflow. Test small/mobile viewports
and Persian formulas. Verify which frontend/backend revision is actually running.

Exercise safe worker stop/resume and injected network/provider failures using the
existing test harness. Show stored work survives and pending work resumes without
duplicates or quota resets. A heartbeat alone does not prove page progress.

Write reproducible defects with steps, expected/actual results, sanitized evidence
and severity. Update operator instructions only for commands you verified or label
them untested. Include how to open the monitor, identify active work, read wait
reasons, stop safely and resume after reboot. Do not advertise 24/7 laptop operation
while asleep or powered off.

Finish with changed files, tests and their actual outputs, unresolved blockers and
the next reproducible action. Close only your finished owned terminals after checking
their process descendants. Preserve active scanners, servers and user shells.
```

## End-of-session message to Sol

```text
Review my completed Freebuff task [ID] using FREEBUFF_HANDOFF.md and the named diff.
Check contract compatibility, correctness, security, tests and existing behavior.
Integrate only the reviewed scope. Do not accept my stated pass count or model
annotation as independent evidence. Return specific corrections or record acceptance
in TASK_BOARD.md, then assign the next unblocked task and writable files.
```
