# HA pass-A handoff — 24 October 2026

Status: local candidate preparation complete; independent pass and human tag
calibration pending. No generation activation, deployment, provider calls or push.

## Prepared evidence

- Fourteen purposively selected math questions from the chosen H0 development
  Maze exam, with exact current question/crop/content/catalogue bindings.
- Fourteen draft annotation records using ST taxonomy/schema0.1, plus fourteen
  inferred design sidecars. Primary/supporting roles and short checkable evidence
  are recorded. Difficulty and distractor mechanisms remain unassigned.
- Thirteen proposed mappings to existing book-backed nodes; one unmapped item.
  These are candidate mappings, not new curriculum or expert confirmation.
- Fourteen proposed answer choices agree with the corresponding published keys.
  This is not independent solving or a scientific correctness certification.
- No holdout question/answer was opened. The sample is developmental, not sealed,
  randomly representative or suitable for statistical quality claims.

Private pack: `backend/data/authoring_work/reasoning-pilot-v1/`.
Its status.json names immutable manifest, annotations, designs, validation and
independent-input artifacts. A hash-named local review HTML contains Persian
primary-label/decision summaries and original source crops. The independent input
excludes pass-A annotations, design advice, answer keys and solution text; selected
publisher solution region references are separately in the manifest. The independent
annotation task is not a blind solver experiment. Do not give the first annotator's
review HTML/results to a second annotator before that annotator saves its outputs.

## Reproducible checks

`backend/scripts/prepare_reasoning_pilot.py` makes bounded immutable private packs,
validates annotations, preserves compatible source formats and never promotes.
Synthetic tests cover reproducibility, changed evidence, second-pass input
separation, invalid tags, unknown knowledge IDs, duplicate numbers and wrong source.
22 reasoning-pilot/contract tests passed.14 real candidates passed structural
validation with0 structural errors and0 eligible records. Human decisions written:0.
The review HTML was structure checked offline; browser file-URL preview was blocked
by browser policy, so no visual browser verification is claimed.

## Predeclared comparison protocol

Freeze the manifest and taxonomy before a second annotation. No model may read
another's annotations before saving its own. Record exact model identification;
pass-A's exact deployment snapshot is unavailable and is stated as such. Compare
objective and representation stages, proposed book-backed IDs, primary technique,
route-aware technique sets and short evidence separately. Report numerators and
denominators, missing/held counts, disagreements and common confusions. Different
valid alternative routes are not automatically errors. With14 purposive cases,
report descriptive counts only; do not rank model quality statistically.

A human reviews uncertain cases, proposed registry changes and a sample of
agreements. Preserve both independent outputs and append human decisions; never
rewrite one to manufacture consensus. The taxonomy stays draft until calibration.
See TAXONOMY_CALIBRATION_PROPOSALS.md for four concrete definition boundaries.

## Exact next handoff / required user action

Open the private hash-named review HTML locally and judge the proposed primary
technique and key decision for each of the14 items. No OCR redo, JSON editing or
full re-solving is requested. Reply by printed number: correct / suggested change /
unsure. An optional separate agent can receive INDEPENDENT_ANNOTATOR_PROMPT.md and
only its allowed inputs; independent results have not been obtained yet.

After human calibration, integrate accepted decisions in a versioned registry
and establish current curriculum/design eligibility. S2 constructor/generator work
remains gated; source text confirmation alone cannot approve inferred labels,
untested generated questions or production activation. Existing answer-crop
boundary limitations from SR_HANDOFF.md remain; this pass does not repair them.
