# Local authoring sandbox handoff — 25 October 2026

Phase 3 has started as an unpublished local generation/verification trial. It is
not a completed production generation stage or release approval.

## Changed implementation

Sol-owned paths: `backend/app/rag/authoring_sandbox.py`,
`backend/scripts/build_authoring_trial.py`, `backend/requirements-authoring.txt`,
`tests/authoring_sandbox_test.py`, `frontend/tools/render-authoring-trial.cjs`
and this handoff. Existing other-agent changes remain untouched.

Eight closed mathematical families construct Persian questions from explicit
specifications. Exact algebra or bounded enumeration checks answers, four distinct
options, branch restrictions and figure consistency. Changed unreviewed wording,
keys, equivalent options and figure parameters fail validation. SymPy is an
optional local authoring dependency, not a production runtime addition.

## Actual evidence

62 integrated sandbox/merge/comparison/pilot/taxonomy tests passed. All eight
candidate checks passed. All 79 formulas rendered without KaTeX errors. Desktop
browser inspection found eight cards, 32 options, one diagram, no horizontal
page overflow and no overflowing formula wrappers. Question-only HTML contains
no embedded answers/proofs; solutions are a separate file. Mobile visual QA was
not performed. No provider calls, paid resources, scans or embedding jobs ran.

Private results: `backend/data/authoring_work/local-authoring-trial-v1/`:
`status.json`, immutable hash-named trial JSON, `questions-only.json`,
`questions.html`, `solutions.html`, `render-validation.json`,
`preview-validation.json` and `novelty-report.json`. Original source records,
frozen snapshots and human receipts are unchanged. Keep artifacts out of Git.

## Evidence boundaries

This is an offline constructor trial, not a benchmark of deployed Groq/Gemini
question generation. It has no independent blind solver and cannot validate
arbitrary model prose. Lexical comparison covers the 40 development stems only;
it does not establish semantic originality, unseen holdouts or corpus-wide
novelty. Book-page references are candidate grounding evidence, with some coarse
mappings, not new human curriculum approval. All eight records remain ineligible.

No difficulty buckets are assigned. Publisher historical labels stay raw in
source analysis; legacy application difficulty settings are unchanged. Technique
tags are not student weaknesses or difficulty measurements.

Q24 exradius support was found on the geometry-book image page 267 (printed266).
The private reference-resolution sidecar records the image hash. Its precise
catalogue mapping remains held; no unrelated node or human approval was invented.

## Next handoff: human quality judgment

Open questions.html first, then solutions.html if desired. Report question
numbers whose wording is unclear, reasoning is too routine, resemblance is too
close, or curriculum is unsuitable. No repeated OCR review is needed. This gate
cannot be satisfied by model agreement or mathematical template checks. After
feedback, revise this small trial before expanding model generation. Human tag
calibration, independent scientific checks, semantic split qualification and
production release remain separate gates. No push, VM changes or activation.

## Actual model trial and follow-up — 25 October

User feedback: the eight constructor questions are good, but some are too similar
to the mock. Record this as set-level positive feedback, not originality approval.

Two bounded live Groq calls used the backend-CWD configuration:
openai/gpt-oss-120b. No private exam/book prose was sent, no holdout was opened,
and existing quota state was preserved. Four model drafts were saved privately
in model-authoring-trial-v1. Three fail mathematics/options/domain checks; one
is mathematically correct but held as a routine unconditional union exercise.
A targeted second prompt did not fix reliability. This tiny synthetic-scope
pilot is not a representative RAG/provider comparison. Do not present it as such.

Reproduction: backend/scripts/check_authoring_model_trial.py. Checks are bound
to exact frozen draft byte hashes, not reusable on revised wording. The second
attempt's conditional probability is 5/18, absent from options. Its quadratic
minimum is 0 (x²−1 is a counterexample), also absent. First attempt's real
coefficient minimum does not exist on its open feasible interval; the solution
silently assumed integer coefficients. Original responses remain unchanged.

New local code: authoring_originality.py screens number-normalized near copies;
question_design.py includes the structural-change contract; exam_style.py applies
this conservative hold to sufficiently long selected reference stems. A screen
pass remains pending semantic review; it is not proof of originality. Threshold
is a conservative engineering heuristic, not calibrated originality accuracy.

model_spec_adapter.py accepts only bounded declarative family/params JSON,
rejects duplicate keys, unsupported parameters, code and model answer fields,
and derives final wording/options/key from the checked constructor. It explicitly
labels outputs supported practice variants, never new designs or eligible items.
This bridge is local and not activated in the live application. It cannot solve
arbitrary model prose or replace expert novelty judgment.

Checks:186 passed/1 skipped (five existing SWIG deprecation warnings) for
originality, question-design, sandbox and corpus tests;14 adapter/originality
tests passed separately. No deployment or database/pool insertion occurred.

Next gate remains calibration of NEW reasoning designs, not approval of the
failed drafts. Existing eight examples establish a promising construction target;
they do not establish that free-form generation meets that target. Before adding
new solver families, obtain a small set of reviewer-accepted structural departures
and bind their mathematical specs to curriculum evidence. No additional PDF upload
or repeat transcription review is currently required.

## Checked-spec integration — 25 October

User feedback is now saved as an immutable, artifact-bound editorial context
record under local-authoring-trial-v1, without issuing scientific, taxonomy,
curriculum or originality receipts. Q6 is flagged as distinctively familiar;
this is not a claim that every shared common exam setup is a copy.

Two new constructor families are implemented in authoring_new_families.py:
quadratic root counting on an open interval (including a distinct double root
and excluded boundary roots), and conditional dice divisibility/prime-sum counting.
These were designed locally, not invented by the provider. They currently lack
fine-grained book-backed catalogue bindings; keep them experimental and ineligible.

run_checked_spec_trial.py made one bounded real Groq gpt-oss-120b request with
synthetic family metadata only. The model selected two allowed typed specs; the
adapter constructed both final questions, wording, options and keys. It does not
accept arbitrary model prose, solutions or code. Output role is explicitly
supported-template selection. Both checks passed.14 formulas rendered without
errors; question sheet has2 cards/8 options and no hidden answer fields. Browser
visual QA is not claimed for this new pair. No inference of originality or release.

Private artifacts: backend/data/authoring_work/checked-spec-trial-v1/ including
raw hash-named model response, checked bundle, status.json, questions.html,
solutions.html, render-validation.json and presentation-audit.json. Previous
trial outputs are untouched. The runner refuses to overwrite an existing status,
so rerunning it does not silently spend quota or replace checkpoint evidence.

Tests independently enumerate exact quadratic roots over97 rational test values
plus boundary cases, and count dice by unordered pairs (each with equal ordered
multiplicity). Key tampering is rejected. This supplements, not replaces, the
analytical solution. The existing8-family construction and copy-screen tests
remain in the integrated suite. No production activation, pool write or deployment.

Next human gate: judge whether the new pair is clear, useful and acceptably
natural for the target exam. This is a short editorial/design calibration, not
another OCR task. General free-form model authoring still fails the prior trial;
these checked templates must not be advertised as fixing unrestricted generation.
Final integrated check:197 passed,1 skipped,5 existing SWIG deprecation warnings (23.78s). No failed tests.

## Calibrated-topic generation trial — 26 October

Prepared grounded_authoring_trial.py and run_grounded_authoring_trial.py for a
three-draft local experiment. The current three scoped summary confirmations are
verified through the existing retrieval audit before preparation/generation.
Four existing educational-book page images were visually inspected by the
assistant. Their byte hashes, page references and the summary receipt are saved
in the private packet under authoring_work/grounded-authoring-trial-v1.
These are test-book references with assistant checks, not official-textbook
review receipts or human scientific review.

The prompt uses a manually prepared projection into three generic mathematics
briefs: cubic identities, parallel-line similarity and modular reasoning.
Private source literals, page images, answer keys, identifiers and receipts are
not sent. This tests limited design guidance; it is not full automatic source
retrieval integration, fine-tuning or a complete novelty benchmark.

Protocol is recorded before generation: three drafts; separate syntax, domains,
existence, mathematical derivation, unique-option/key, structural-departure and
render checks. No generated item can become eligible from this runner. A syntax
pass explicitly does not mean a mathematically correct question. One generate
invocation per saved attempt; the existing client may perform transport retries.
Existing terminal credential/quota blocks are respected, not cleared. The runner
refuses reuse of an attempt and checks source bindings again after a response.

Live results so far are provider/network failures, with no saved question batch:
the primary Groq credential was already access-blocked; one other credential
returned access denial. Gemini direct requests timed out/failed TLS. After the
user enabled the VPN, the loopback HTTP proxy listened but credential-free tests
through it to Google, Gemini and Groq all timed out. A client-specific proxy retry
also failed TLS. Application .env files were not changed. One initial interrupted
attempt has an unknown request outcome; do not assert zero consumption for it.
Raw status/log checkpoints and recovery notes are preserved privately.

53 focused offline tests passed, covering the new draft contract, calibrated
bindings, checked families, safe adapter and originality screen. Python compile
checks passed. No new generation-quality result, release, pool insertion or
production activation is claimed. No VM work or push.

Next handoff: after a working VPN/proxy route is confirmed, from backend run
the trial's prepare action with a fresh attempt number, then generate with the
same number, --provider gemini --use-local-proxy. Attempt7 is next available.
The new credential-free transport preflight will hold a broken connection before
calling the model. Preserve prior attempts. Inspect actual saved drafts, derive
their answers independently, record rejection reasons and render only surviving
items. Do not ask again for the three source-summary confirmations or mark the
whole S2 stage complete based on this experiment.

## Resumed trial and review handoff — 27 October

The user resumed work and enabled the proxy. Source audit still retrieves the
same3 confirmed summaries,0 evidence holds,6 local routing regressions passing.
Explicit high reasoning with an initial16384-token completion budget is now bound
to each new trial packet. OCR settings and application .env files are unchanged.

Actual saved outcomes in grounded-authoring-trial-v1:

- Attempt7, Gemini:503 demand failures; no usable draft.
- Attempt8, Groq high reasoning:3 drafts. Independent symbolic/finite checks found
  2 correct but routine items (held for design quality) and1 underdetermined
  geometry item with incorrect triangle correspondence (rejected). The frozen
  response is bound in check_grounded_authoring_trial.py and its private report.
- Attempt9, Groq revised design guidance:4 provider JSON-validation failures;
  no usable batch. Do not label these as mathematical rejections.
- Attempt10, Gemini revised guidance:3 new questions with valid keys after bounded
  checks. HTTP evidence records2 transient503s, a retained partial reply and final
  successful reply. Existing client retries can increase output budget on truncation.
  Token usage in status.json is the final successful response, not cumulative cost
  or a claim of zero consumption for failed/partial responses.

check_revised_grounded_trial.py verifies the exact frozen response bytes and
current source packet. It independently derives the algebra feasibility bound
using a quadratic discriminant, checks the geometry under general shear and15
exact coordinate examples, and enumerates all60 integers for the modular count.
Correct answers are5,4,8 respectively. These are assistant checks, not human
scientific approval or a universal solver. No semantic originality guarantee.

Raw drafts are preserved. A separate review revision adds a sufficiency argument
to algebra, corrects the geometry parallelogram order and its unsupported
wrong-route example, and repairs one known JSON/LaTeX escape in design metadata.
The question stems, options and keys are unchanged. An original Windows newline
translation was detected; both stored byte and normalized response-text hashes
are explicitly bound. Future raw/fragment writes preserve exact UTF-8 bytes.

The runner now honors the local proxy for Groq as well as Gemini, classifies
503/access/quota/transport failures separately, and preserves visible response
fragments without request headers or hidden reasoning. Strict draft validation
holds unexpected control characters caused by mis-escaped LaTeX.

The renderer now handles multiline $$...$$ cases without stray delimiters and
uses neutral provenance wording for both constructed and free-form questions.
65 focused tests pass, including real rendering, answer-sheet separation and
escaped presentation text. Reproducible math scripts pass. Preview has3 cards,
12 options,1 geometry diagram,40 formulas and0 rendering errors. Browser checks
showed the desktop algebra view and narrow geometry view; browser-qa.json and a
screenshot are saved. Broader device coverage is not claimed.

Review URL: http://127.0.0.1:8773/questions.html (loopback only). Static fallback:
backend/data/authoring_work/grounded-authoring-trial-v1/attempt-10/review-v1/questions.html.
Answers are on the separate solutions.html. The isolated preview server's PID
is saved in that folder; it serves only this review revision. Trial processes
completed. No scanning, pool generation, deployment, policy activation or push.

Next required human input: read the3 NEW questions and judge clarity, exam
likeness and perceived imitation. Give question numbers and specific concerns;
no repeat OCR/source review or raw JSON editing is requested. Sol then records
the scoped feedback, fixes issues and continues the technical workflow. Keep
H3/scientific/novelty/release gates distinct; a positive editorial response must
not approve all source annotations or activate the production bank.
