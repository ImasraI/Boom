# Next authoring iteration: discriminating questions and readable figures

Status: local design requirements following owner feedback on G01–G06,
30 October 2026. No production promotion or new model trial is implied.

## Editorial evidence

G01 was rejected as too direct and poorly visualized. G03 was described as a
familiar textbook exercise, possible as a very easy exam item. G02, G04, G05 and
G06 were accepted as Konkur-like; G05 was also somewhat familiar. These are
question-version-bound editorial judgments, not population-calibrated difficulty,
scientific certification, formal technique approval or a model comparison.

The new target is a consequential mathematical decision, not more equations or
mandatory topic combinations. A one-equation solution can still be insightful;
G01 specifically did not earn that judgment from the reviewer. G02's combination
of constraints is a useful positive example, not a recipe all questions must copy.

## Figure contract

Separate the mathematical specification, its illustrative construction and the
screen layout. A schematic may be not to scale, but must preserve incidence,
point order, inside/outside status, crossings, relevant parallel/perpendicular
relations, stated angles and tangency/secancy. Never make a secant look tangent
or move a point off its stated line merely to separate labels. If exact metric
proportions are relaxed, identify the figure as schematic and record which metric
constraints are intentionally not asserted; do not let it pass an exact audit.

For nested lengths PA and PB on one ray, offset their dimension guides or labels,
not the underlying mathematical ray. Improve endpoint marks, contrasting segment
styles, whitespace and label offsets; offer a detail inset when needed. A global
zoom cannot fix a tiny segment relative to the whole shape.

Preferred construction order:

1. Select valid parameters from the mathematical family.
2. Construct and verify exact geometry.
3. Project at the intended desktop and mobile display sizes; inspect short
   segments, near-tangencies, overlaps, label collisions and cropping.
4. Reject/resample poor parameters or reposition labels before considering a
   declared schematic. Pixel thresholds are usability heuristics, not mathematical
   proof or a substitute for visual review.
5. Preserve the original image, mathematical audits and presentation changes as
   different revisions. Do not silently repair the rejected G01 and call it a new
   creative question.

## Distractors as falsifiable error hypotheses

The question and correct solution must remain unambiguous. Put the intentional
error in a plausible wrong solution and its resulting option, not in the givens.
Do not claim most students make an error without observed responses.

Each proposed distractor needs a sidecar record with:

| Field | Meaning |
| --- | --- |
| `option_index` | Which incorrect option the proposal explains |
| `error_hypothesis` | A specific wrong assumption or operation |
| `wrong_step` | The first invalid mathematical statement |
| `derived_result` | The value/set actually produced by that wrong route |
| `why_invalid` | A checkable explanation tied to the givens/domain |
| `validation_state` | Unchecked, assistant-checked, expert-reviewed; distinct evidence |
| `observed_selection_count` | Null until real student data exists |

Reject a distractor story if its trace does not produce the option, if it changes
several assumptions without explanation, or if it is another valid answer under
an unstated convention. Screen equivalent options and alternate interpretations.

Useful error hypotheses include full secant versus external segment, excluded
root versus admissible root, local bound versus attainable global bound, necessary
versus sufficient condition, strict versus inclusive endpoint, and an isometry
applied after its hypotheses have changed. Use only hypotheses relevant to the item;
do not insert every trap into every question.

## Guessing and shortcut audit

Separate unsupported guessing from legitimate efficient reasoning. Testing answer
choices, exploiting symmetry, bounding, or choosing a discriminating value can be
a valid complete solution. Preserve and teach such a route when its conditions
are satisfied. The objective is to avoid unintended answer leakage, not to force
students through the author's longest solution.

For each new candidate record:

- An answer-withheld solve before seeing options, checking underdetermination.
- An option-aware solve to discover valid elimination and back-substitution paths.
- Tested attack hypotheses: obvious scale/sign/unit mismatch, inadmissible values,
  one isolated option format, diagram measurement, symmetry/equality guessing,
  lucky special cases and answer cues in wording.
- For a guessed test case, whether it satisfies every given and whether the result
  holds for all admissible cases. One example does not prove a universal claim.
- A declared outcome: valid shortcut, unintended leakage, unsupported guess,
  unresolved. Model agreement alone does not resolve this classification.

An immediately valid sign/bound argument may be intentional. If it bypasses the
intended learning objective accidentally, redesign the constraints/options and
recheck the entire question; do not just obscure the clue with awkward numbers.

## Fast-solution library

Store fast routes separately from the full explanatory solution. Each entry needs
an immutable question-revision binding, method, applicability conditions, concise
derivation, equality/domain cases, a failure counterexample or explicit absence,
evidence and review state. Candidate techniques can reference the draft taxonomy;
do not invent an approved tag or a student's weakness from one route.

Human suggestions are valuable. The owner can submit a question ID and a short
route, such as a symmetry pairing or option test. Sol checks the proof and conditions;
an expert resolves ambiguous mathematics where needed. Keep rejected and corrected
routes versioned. Use reviewed examples for retrieval later; do not say API keys
were trained or that a route is faster without a defined comparison or timing data.

## Bounded next experiment

Prepare a small new design set, retaining G02/G04/G05/G06 as editorial anchors and
G01/G03 as rejected/routine examples. Do not rewrite frozen pilot outcomes.
Before any call, freeze task briefs, design hypotheses, option-error hypotheses,
figure readability checks, shortcut audit and acceptance criteria. New sidecar
proposals are not mandatory new fields in the compatible v0.2 question schema.

Evaluate correctness, solution completeness, visual legibility, discriminating
decision, distractor validity and shortcut behavior separately. Preserve failures.
Human next is review of the resulting new/revised candidates, not another request
to repeat the G01–G06 feedback already given. No holdout access, deployment or paid
resources are authorized by this document.
