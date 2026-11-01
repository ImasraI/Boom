# Local paired benchmark operations

This is a development comparison of generic reasoning guidance across three math
topics. It is not final holdout evaluation, publication approval or a full-mock
quality estimate. Existing source confirmations and frozen holdouts are preserved.

Run commands in PowerShell from the backend directory:

```powershell
cd C:\Users\Arsam\Desktop\Boom-merged\backend
.venv\Scripts\python.exe -X utf8 scripts\run_authoring_benchmark.py status
.venv\Scripts\python.exe -X utf8 scripts\run_authoring_benchmark.py run --provider gemini
```

The runner resumes untouched items only. An OS lock rejects simultaneous runs.
Never erase assignment.json, item states, transport journals or provider quota
state to restart it. A corrupted checkpoint raises an error rather than becoming
a new attempt. Provider/model, prompt hashes and paired settings are frozen.
Provider refusals, protocol defects, transport failures and interrupted unknown
consumption remain separate outcomes. Failed items are not silently replaced.

To stop after the current request, run this in another terminal:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\run_authoring_benchmark.py stop
```

The persistent stop-request.json requires deliberate acknowledgement before a
later resume. It is not cleared automatically. Network failure stops before a new
authenticated request; check the VPN/proxy before resuming. Known daily/access
blocks are respected individually; terminal errors are not repeatedly probed.
Temporary provider overload pauses after three consecutive failed items. Do not
resume before the saved retry_not_before. No model switch is made mid-experiment.

Private artifacts stay in ignored backend/data/authoring_work/development-benchmark-v1.
run-status.json shows actual progress and observed HTTP responses; these counts
are not promises about consumed quota. Missing usage/response information is
unknown. Generated content and failed visible fragments stay private; request
headers, keys and hidden reasoning are not exported. No application DB, bank,
deployment, billing or production activation is part of these commands.

After generation has final outcomes for all40 planned items, Sol runs:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\prepare_benchmark_review.py
.venv\Scripts\python.exe -X utf8 scripts\solve_benchmark_blind.py
```

The first command freezes a blinded review revision. Only typed geometry becomes
SVG; model-supplied HTML/SVG is never executed. Math-rendering failures stay visible
as escaped formulas with warnings and a report, without dropping the question.
Question pages contain no answers or arm/provider identifiers. The private
binding maps R aliases to original items. Answer claims are on a separate page.

The second command sends only five question stems/options per group to the
existing free Groq solver. It receives no author keys, solutions, designs, source
examples or held-out papers. Each group is checkpointed once; interrupted unknown
consumption is preserved rather than automatically retried. Agreement is supporting
evidence, not human/scientific review. Disagreements require mathematical inspection.

Sol also owns independent derivations and figure/domain checks. The first six
algebra drafts have a separate hash-bound symbolic replay in
check_benchmark_algebra_slice.py; none of the other drafts inherit those checks.
Literal/number-masked duplicate screening cannot establish structural originality.

Human input comes after a concrete checked batch exists: assess clarity, natural
Konkur likeness and repeated construction separately, using neutral R aliases.
Scientific correctness remains a separate evidence dimension. No reviewer is
asked to approve the previous three calibration questions again. Human rating
anchors remain a draft pending calibration; no student difficulty is inferred.

## Partial snapshot and request-size recovery

When generation is explicitly waiting/stopped, prepare_benchmark_review.py
--partial freezes only saved drafts, retaining40 planned slots and their pending
states. It refuses an in-flight item and cannot label the comparison complete.
solve_benchmark_blind.py --partial checks that explicit snapshot. Existing final
group outcomes are preserved on resume; untouched groups may use a nonblocked
credential. Rate/size refusals are not question-quality failures.

An explicit second verification protocol, solve_benchmark_blind.py --recover-small,
retains previous failures and reparses original responses before reuse. It sends
one previously unverified question at a time, with high reasoning and a declared
4096-token completion budget. This reduces the request envelope after413 failures;
it does not change the frozen Gemini authoring experiment or silently replace
failed results. Completed recovery comparisons are replayed and their totals
checked on resume. In the current snapshot,18 distinct questions matched and3
remain provider-held. Do not reset these records to force more attempts.

check_benchmark_saved_slice.py replays the21 exact saved answer checks locally.
check_benchmark_figures.py audits the8 original coordinate diagrams; strict
tolerance flagged3. build_benchmark_checked_preview.py creates a separate repaired
presentation, binding every delta and independent proof to its original hash.
Raw outcome metrics are unchanged; human feedback applies to that new version.
The current served URL is in the latest README. Sol still owes completion of
the8 untouched generation items after the saved daily retry time, followed by
full-batch consolidation. No automatic retry schedule has been installed.

28 October continuation supersedes the pending8 instruction: all40 attempts are
now final, with24 drafts. --project-keys was explicitly authorized by the user;
it rotates eligible credentials from active backend and OCR-worker envs while
retaining the frozen provider/model, actual scanner/pool refusal state and all
earlier outcomes. Its scope receipt records counts, never keys. Backups are excluded.

carry_benchmark_verification.py --prior-review <review-revision-name> reparses
original batch and small-packet solver responses before carrying identical raw
candidate/literal/key evidence to a newer review. Changed protocols, literals,
keys, approvals and false comparison states are rejected. It currently carries18
matches with0 provider calls, leaving6 without blind comparison. This transfers
no figure or human-science approval. The new display is a distinct repaired
revision; the raw comparison evidence is not relabeled as a fresh solve.
