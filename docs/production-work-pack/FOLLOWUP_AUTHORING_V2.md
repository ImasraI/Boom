# Follow-up authoring experiment — draft v0.2

30 October 2026. Local preparation only. The original benchmark, model outputs,
review bindings and provider-refusal states must remain unchanged.

## Human feedback now available

The user describes the 24-question sample as great overall, but its geometry
questions are too similar and all use Thales' theorem. This is qualitative,
answer-bearing editorial feedback, not per-item numeric ratings, a blinded arm
comparison, scientific approval, formal tag approval or production release.
Do not ask for the same overall editorial confirmation again.

The user's subsequent clarification narrows that judgment: these questions are
great and Konkur-worthy if the prompts requested Thales geometry and modular
discrete mathematics. They did. Record positive editorial feedback within those
requested families. This did not test broad geometry/math coverage; coverage is
a new experiment, not an established failure to follow general-topic prompts.
The clarification has a separate hash-bound receipt preserving earlier feedback.

The frozen task set explains much of this: all seven geometry specifications
use the `parallel_similarity` brief, with parallel-section/similarity facts.
Eight geometry drafts survived, alongside eleven cubic-identity and five
modular-cycle drafts. These are instruction-family counts, not independently
adjudicated technique labels or a broad test of geometry capability.

## Next technical work

1. Prepare six geometry design briefs with different essential mechanisms, using
   current book-backed catalogue nodes and inspected textbook evidence. Candidate
   areas include circle length/angle relations, cyclic configurations,
   transformations, areas, trigonometric geometry and loci. Existing catalogue
   presence is a mapping lead, not automatic source eligibility or clean OCR.
2. Reserve at most one primary similarity/Thales construction in that pilot.
   A question with a different diagram but the same essential solution chain
   remains the same mechanism family. Merely claiming a different tag does not
   satisfy the diversity target.
3. Keep the mathematical scope and source/evaluation exclusions explicit. Unknown
   catalogue IDs, unsupported theorems and unreviewed source examples stay held.
   Do not expose held-out papers or their answers during authoring.
4. Freeze a new protocol and prompt hashes. This pilot changes task coverage and
   explanation requirements; it is not another arm of the original comparison.
5. Generate only after each selected brief has factual evidence. Apply separate
   mathematical, option, diagram, duplication and pedagogical checks. Preserve
   failures; do not silently substitute a convenient successful item.

## Student-facing solution requirements

The new output must retain the question, four options, answer, design and figure,
but supply a separate pedagogical solution with:

- `key_observation`: explain why the chosen idea applies to the actual givens.
- `steps`: ordered records with stable step ID, explanation and mathematical
  assertion. Do not skip the step connecting the givens to the key observation.
- `proposed_techniques`: draft taxonomy IDs with primary/supporting/check roles,
  referenced step IDs and short checkable evidence. Unknown labels remain
  unresolved. These are proposals, not human-approved annotations.
- `boundary_checks`: relevant domain, sign, degeneracy and attainability cases.
- `answer_justification`: explain why the chosen option follows and is unique.
- `alternative_route`: optional, explicitly null if none is supplied.

Keep a separate `verification_record` for symbolic identities, finite enumeration
or numerical checks. Verification is not a substitute for the teaching solution.
Enumeration is legitimate when it is the natural complete argument for a small
sample space; reject avoidable exhaustive listing when a claimed cycle/invariant
or other insight is never explained. Do not infer difficulty from step/tag count.

For symmetry specifically, state the transformation and what is preserved. A
symmetric expression alone does not justify setting variables equal. An extremum
needs a global bound and an attainable equality case.

## Evidence and handoff

The scoped receipt and task-family audit are private under
`backend/data/authoring_work/development-benchmark-v1/editorial-feedback/`.
The accepted style feedback closes this sample's qualitative editorial request
with the stated geometry reservation. It does not close production S2/S3, final
holdout evaluation, full source qualification or release gates.

Next owner: Sol. Inspect the candidate textbook evidence, implement/test the new
solution contract and mechanism coverage check, then prepare the bounded pilot.
No new human source request is needed merely to begin those technical steps.

## Execution checkpoint — 30 October

The six mechanisms were prepared and attempted with frozen prompts, catalogue
and page-image bindings. Original outcomes: two structured drafts, two provider
failures, two JSON-format holds. A separate recovery after the user changed VPN
returned the two missing structured drafts. Minimal recorded format projections
make the two held responses inspectable while preserving their original outcomes.

Six keys have exact assistant derivations; five have answer-withheld solver
matches. The cyclic solver failed provider JSON generation, not a mathematical
disagreement. The new review includes the complete Gemini solutions and proposed
step-linked techniques. No held-out exam or raw source question was supplied.

Observed limitations are concrete: three structured teaching sections are English;
circle/cyclic coordinates required correction; reflection's illustration reveals
the solving construction, and its opposite-side counterfactual is wrong; Heron's
alternative only computes the isosceles area without proving maximality; altitude
sufficiency is implicit in the author explanation. Independent notes supply the
missing arguments/corrections while preserving author text for inspection.

The combined six-item snapshot is referenced by ignored
`backend/data/authoring_work/pedagogical-geometry-v2/combined-review-pointer.json`.
Next qualitative review concerns these six mechanisms, not another confirmation
of the original 24 narrow-family questions. A subsequent prompt revision must be
new and explicit; no silent edits to this pilot or its failed attempts.

The owner has now supplied the six-item editorial review: G01 rejected as direct
and visually weak, G03 routine/very easy, G02/G04/G05/G06 accepted with familiarity
noted for G05. The next design requirements and the fast-solution workflow are in
[AUTHORING_DISTRACTORS_AND_SHORTCUTS.md](AUTHORING_DISTRACTORS_AND_SHORTCUTS.md).
Do not ask for the same review again or turn these judgments into scientific or
population difficulty labels.
