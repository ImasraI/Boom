# Question reasoning taxonomy — candidate v0.1

Prepared 22 October 2026. Proposed registry, not an implemented contract or
question approval. Use with [QUESTION_DESIGN_SCHEMA.md](QUESTION_DESIGN_SCHEMA.md) and the
[production work pack](production-work-pack/README.md). Existing source,
curriculum, review and release rules continue to apply.

## 1. Purpose and boundaries

Describe observable solution methods for retrieval, varied authoring and label
improvement. Do not reconstruct an author's private thoughts. Use equations,
counterexamples, conditions or cited figure features as evidence.

Keep these axes separate:

| Axis | Records | Does not establish |
| --- | --- | --- |
| Knowledge | Existing textbook catalogue IDs and supporting pages | New curriculum inferred from an exam |
| Technique | Operations used by a defensible solution route | A unique intended solution |
| Representation | Given, constructed and requested forms | Reasoning merely because a picture exists |
| Objective | What the question asks the solver to determine | The method used |
| Check/shortcut | Validation or reduced-work tactic, with conditions | A complete proof by itself |
| Misconception | A specific plausible error tied to evidence | A student's diagnosed weakness |
| Difficulty | Intended demand and separate observed measurements | Difficulty determined by tag count |

Knowledge mappings must use IDs already present in the supplied, versioned
textbook catalogue, with source support. The current curriculum loader is
`backend/app/rag/book_curriculum.py`; distinguish its lesson/node IDs from
database book identifiers. Never mint a chapter, lesson or prerequisite ID.
Unmapped knowledge stays empty with an issue; propose catalogue review separately.
Textbooks define allowed content; exams supply authoring examples.

## 2. Minimal start and technique registry

IDs are stable ASCII; English/Persian names are display labels. Start with
knowledge, objective, representation, a route and applicable **Core** techniques.
Use expansion labels when supported, without quotas. Empty optional arrays are
valid; use `unresolved` for incomplete assessment, not `none`.

Every row gives an inclusion example and a boundary. All examples are synthetic.

| ID | English / فارسی | Include; exclude |
| --- | --- | --- |
| `tech.equation_setup` **Core** | Equation setup / تشکیل معادله | Translate relations into constraints, e.g. equal travel times; exclude copying an already supplied equation. |
| `tech.substitution` **Core** | Change of variable / تغییر متغیر | Introduce an equivalent simpler variable or expression, e.g. t=x+1/x with its admissible range; exclude merely inserting known numbers into a formula. |
| `tech.direct_substitution` | Direct substitution / جایگذاری مستقیم | Evaluate a supplied or established relationship with known values; exclude a structural change of variable. This routine tag does not establish a conceptual insight. |
| `tech.graph_visual` **Core** | Graph/visual reasoning / استدلال نموداری و تصویری | Infer from slope, signed area, geometry or spatial relations; exclude decorative figures or reading one printed label. |
| `tech.relevance_selection` **Core** | Relevant information selection / انتخاب اطلاعات مرتبط | Identify which competing givens affect the target; exclude ordinary use of the only given. |
| `tech.case_analysis` **Core** | Case analysis / بررسی حالت‌ها | Partition an exhaustive domain, e.g. positive/negative branches of an absolute value; exclude a few illustrative trials. |
| `tech.domain_checks` **Core** | Domain checks / بررسی دامنه | Enforce admissibility, e.g. denominator nonzero or physical time nonnegative; exclude an unsupported plausibility judgment. |
| `tech.limiting_cases` | Limiting cases / حالت‌های حدی | Examine a boundary or limiting regime, e.g. friction tending to zero; exclude general small-number examples. A limit alone need not solve the original instance. |
| `tech.dimensional_analysis` | Dimensional analysis / تحلیل ابعادی | Compare dimensions or derive admissible form, e.g. reject adding length to time; exclude unit conversion alone. |
| `tech.approximation` | Approximation / تقریب | Use a justified estimate with sufficient error control, e.g. a bound separating options; exclude unjustified rounding near a decision boundary. |
| `tech.optimization` | Extremum analysis / تحلیل بهینه‌سازی | Compare critical points, active constraints or boundaries to establish an attainable extremum; state the actual method (derivative, inequality, monotonicity, etc.). Exclude tagging solely because the question asks for a maximum. |
| `tech.symmetry` | Symmetry / تقارن | Use a transformation preserving relevant structure, e.g. pair equal contributions; exclude visual resemblance without justified equality. |
| `tech.worst_case` | Worst-case reasoning / بررسی بدترین حالت | Analyze the most adverse admissible arrangement to establish a guarantee; exclude ordinary extremization without a guarantee objective. |
| `tech.counterexample` | Counterexample / مثال نقض | Give an admissible instance refuting a universal claim; exclude confirming examples or an instance outside the domain. |
| `tech.small_cases` | Small cases / بررسی حالت‌های کوچک | Solve small instances to discover or test structure, e.g. counts for n=1,2,3; exclude treating a finite pattern as proof for all n. |
| `tech.repeated_unit_counting` | Repeated-unit counting / شمارش واحد تکرارشونده | Count equal blocks and handle boundaries/overlap, e.g. tiles in repeated strips; exclude multiplication with no repeated structure. |
| `tech.option_elimination` | Option elimination / حذف گزینه | Reject choices using necessary conditions; exclude merely matching a fully calculated answer to its option. |
| `tech.invariants_conservation` | Invariants/conservation / ناورداها و پایستگی | Track a quantity unchanged by allowed operations, e.g. parity or conserved charge; exclude assuming conservation when its conditions fail. |
| `tech.work_backward` | Work backward / حل از انتها | Reverse constraints from a target to permitted initial states; exclude ordinary forward substitution. Check reversibility. |
| `tech.bounds` | Bounds / کران‌گذاری | Constrain a value enough to answer, e.g. an interval containing exactly one option; exclude an unexplained estimate. |
| `tech.complement_counting` | Complement counting / شمارش متمم | Count the total minus excluded outcomes; exclude subtraction without a defined common sample space. |
| `tech.representation_change` | Representation change / تغییر بازنمایی | Convert meaningfully, e.g. a verbal condition into a graph or a geometric relation into algebra; exclude cosmetic notation changes. |

Use overlapping labels only with distinct evidence; equation setup does not
automatically imply representation change. Worst-case,
optimization and bounds can coexist; explain the guarantee, extremum and bound
separately. Small cases suggest; counterexamples refute; exhaustive case analysis
can establish a result. None inherently means “hard.”

## 3. Representation and objective registries

Representation entries include `stage: given | constructed | requested`.
Multiple entries express mixtures; avoid a vague `mixed` label.

| ID | English / فارسی | Include; exclude |
| --- | --- | --- |
| `rep.verbal` | Verbal / کلامی | Prose conditions; exclude incidental instructions. |
| `rep.symbolic` | Symbolic / نمادی | Equations, expressions or symbolic answers; exclude isolated numbering. |
| `rep.graph` | Graph / نمودار | Axes and functional/statistical plots; exclude a circuit schematic. |
| `rep.geometry` | Geometric / هندسی | Spatial shapes and geometric relations; exclude decorative shapes. |
| `rep.table` | Tabular / جدولی | Structured data cells; exclude options merely laid out in rows. |
| `rep.schematic` | Schematic / شماتیک | Circuits, apparatus or process diagrams; exclude a plotted function. |
| `rep.chemical` | Chemical notation / نمادگذاری شیمیایی | Formulae and reaction notation; exclude any equation simply appearing in chemistry. |

Label the requested objective.

| ID | English / فارسی | Include; exclude |
| --- | --- | --- |
| `obj.determine` | Determine / تعیین | Obtain a value, expression or configuration; exclude counting a collection. |
| `obj.compare` | Compare / مقایسه | Order or compare quantities; exclude incidental comparisons within a calculation. |
| `obj.count` | Count / شمارش | Determine the number of admissible outcomes or objects; exclude a probability as the requested final quantity. |
| `obj.probability` | Probability / احتمال | Determine the chance of an event under a specified model; counting may support the solution but is a separate technique. |
| `obj.evaluate_claim` | Evaluate claim / ارزیابی گزاره | Establish/refute truth, possibility or necessity; exclude merely choosing a numerical answer. |
| `obj.interpret` | Interpret / تفسیر | Explain meaning or infer a relationship from evidence; exclude direct transcription. |
| `obj.extremum` | Extremum / مقدار حدی | Find a maximum/minimum over admissible choices; exclude routine numerical ordering. |
| `obj.guarantee` | Guarantee / تضمین | Find what must hold in every allowed configuration or a threshold ensuring it; exclude the outcome of one favorable case. |

## 4. Checks, shortcuts and misconceptions

Check/shortcut entries reference a route and, where applicable, its technique
ID. They describe function, not a second mandatory technique count.

| ID | English / فارسی | Include; exclude |
| --- | --- | --- |
| `check.units` | Unit consistency / سازگاری واحدها | Check dimensions or conversion factors; exclude claiming units prove a coefficient. |
| `check.admissibility` | Admissibility / مجازبودن جواب | Check domains, signs and physical constraints; exclude unexplained “reasonable.” |
| `check.residual` | Substitute back / جایگذاری جواب | Test the candidate in original conditions; exclude checking only a transformed equation. |
| `check.independent_route` | Independent route / مسیر مستقل | Cross-check through a distinct derivation; exclude paraphrasing the same calculation. |
| `shortcut.options` | Use option structure / استفاده از ساختار گزینه‌ها | Eliminate or test choices under explicit conditions; exclude random guessing. |
| `shortcut.estimate` | Sufficient estimate / تخمین کافی | Bound error enough to decide; exclude a loose estimate that leaves alternatives. |

Misconceptions are optional hypotheses about item/distractor design. Include an
option reference and the incorrect operation producing it. If no such evidence
exists, leave empty. Suggested bounded initial labels:

| ID | English / فارسی | Include; exclude |
| --- | --- | --- |
| `mis.sign` | Sign error / خطای علامت | Reversing a signed term; exclude an unexplained wrong answer. |
| `mis.domain` | Ignored domain / نادیده‌گرفتن دامنه | Accepting an inadmissible root; exclude a valid alternate domain interpretation. |
| `mis.units` | Unit mismatch / ناسازگاری واحدها | Missing a conversion factor; exclude unrelated arithmetic. |
| `mis.angle_unit` | Degree/radian confusion / اشتباه درجه و رادیان | Using the wrong angular unit; exclude all trigonometric errors. |
| `mis.graph_quantity` | Graph quantity confusion / اشتباه در کمیت نمودار | Confusing height, slope or area; exclude an unreadable axis. |
| `mis.overcount` | Overcounting / بیش‌شماری | Counting the same outcome twice; exclude missing outcomes. |
| `mis.illegal_operation` | Invalid algebraic operation / عمل جبری نامعتبر | Dividing by a possibly zero expression; exclude a transcription defect. |

One wrong response does not diagnose a weakness. Student evidence requires
separate repeated observations, exposure history and uncertainty; do not infer
ability or remediation automatically from these annotations.

## 5. Routes, evidence and difficulty

Route roles are `primary` or `alternative`; “primary” names the annotator's
chosen route, not the author's intention. Within routes, technique roles are `primary`
(decisive), `supporting` (enables it), or `check` (validates it). A distinct
alternative route can have its own primary technique. Do not force a unique
method or enumerate every imaginable solution.

Attach brief checkable evidence to each annotation: an equation, admissible
example, cited region or explicit constraint. Retain evidence references to
the exact question/content/figure version, annotator/model and prompt version.
Keep original text, ordered options, key provenance and annotations separate.
Ambiguous OCR, missing figures, questionable answer association or unresolved
correctness puts the affected record on hold. Do not repair source uncertainty
by guessing which reading gives a convenient answer.

Intended difficulty uses existing levels `easy`, `konkur`, `hard`, `extreme`
or null, with observable demand such as case distinctions or concept combinations.
Extreme stays within the permitted curriculum. Empirical difficulty remains
null until response data exist; then record first-attempt accuracy, sample size,
time distribution, prior exposure, assignment method and uncertainty. Record
discrimination separately when supported. Neither many tags nor model agreement
establishes difficulty, correctness or human review.

## 6. Example annotation envelope

This synthetic format example cannot be ingested or released. Review any
production adapter; do not overwrite the existing question schema.

```json
{
  "annotation_schema_version": "0.1",
  "taxonomy_version": "0.1",
  "question_ref": "synthetic:constant-speed:v1",
  "source": {"content_sha256": null, "figure_sha256": null},
  "catalogue_version": null,
  "knowledge_ids": [],
  "objective": "obj.determine",
  "representations": [
    {"id": "rep.symbolic", "stage": "given"},
    {"id": "rep.graph", "stage": "constructed"}
  ],
  "routes": [
    {"id": "r1", "role": "primary", "annotations": [
      {"id": "tech.equation_setup", "role": "primary",
       "evidence": "For constant v=3 m/s over 2 s, displacement=v*t."},
      {"id": "tech.direct_substitution", "role": "supporting",
       "evidence": "3*2=6 m."}
    ]},
    {"id": "r2", "role": "alternative", "annotations": [
      {"id": "tech.graph_visual", "role": "primary",
       "evidence": "Construct horizontal v=3 on [0,2]; signed area=6 m."}
    ]}
  ],
  "checks_shortcuts": [
    {"id": "check.units", "route_id": "r1", "evidence": "(m/s)*s=m."}
  ],
  "misconceptions": [],
  "intended_difficulty": {"level": null, "rationale": null},
  "empirical_difficulty": null,
  "annotator": {"kind": "model", "model": "record actual identifier", "prompt_version": "0.1"},
  "review": {
    "annotation_state": "candidate", "source_state": "synthetic",
    "scientific_state": "not_checked", "human_reviewed": false,
    "eligibility": "held", "issues": ["synthetic_example", "curriculum_unmapped"]
  }
}
```

## 7. Independent development pilot and revision

Assign at most 50 initial development questions covering available subjects,
figures and route complexity. Freeze manifest, versions and taxonomy. Keep whole holdout
papers and related variants out of prompts, retrieval and tuning. If exposed
for improvement, move them to development and replace the holdout.

Claude and Astra independently annotate the same manifest; neither sees the
other's outputs until both are saved. Record actual model/version and evidence
access. Independence is procedural, not proof of independent errors. A reviewer
adjudicates disagreements; a qualified human also samples agreements and checks
new/rare labels and uncertain science. Preserve original annotations alongside
decisions; model reconciliation is still candidate evidence.

Report per-axis/label agreement, prevalence, missing/held rates and sample sizes.
Compare route-aware sets, primary choices and evidence
quality separately; exact record equality is too strict. Two valid alternative
routes may differ without error. Show common confusion pairs and reviewed
false inclusions/omissions. With small samples or rare tags, avoid confident
rankings. Refine definitions rather than forcing tag consensus.

A registry-change proposal includes: proposed ID/action (`add`, `merge`,
`split`, `rename`, `deprecate`), definition, positive/negative examples,
conflicting existing IDs, observed counts, evidence references, expected benefit,
compatibility impact and reviewer decision. An agent may propose, never
unilaterally change the shared registry/schema. Absence in 50 items is not enough
to delete a useful label. Approve versions explicitly; retain deprecated IDs,
aliases and an old-to-new migration table. Splits require reannotation when
old evidence cannot resolve the branch. Never silently reinterpret old records.

## 8. Copyable agent assignment

```text
Read docs/QUESTION_REASONING_TAXONOMY.md and docs/QUESTION_DESIGN_SCHEMA.md.
Annotate only the assigned development manifest (initially <=50 questions)
using taxonomy v0.1 and the supplied catalogue/version. Do not access holdouts.
Resolve knowledge only to existing source-supported catalogue IDs.
Inspect source crops, ordered options and answer provenance. Hold uncertain
source/answer/scientific evidence; do not guess missing content or reviews.
Write candidate annotations with short checkable evidence and useful primary/
alternative routes, distinguishing supporting techniques and checks. Do not
infer author thoughts, difficulty from tags, or weaknesses from one response.
Leave unsupported fields empty/null and record unresolved issues.
Work independently: do not read another annotator's output before submission.
Return annotations, coverage/held counts, disagreements with definitions,
and separate add/remove/merge/split proposals with examples and migration impact.
Do not modify shared schemas, application code, approval states or this registry.
Use only assigned local files and already-authorized free resources within
actual quotas. No VM access, corpus upload, billing, paid compute, push or keys
in output. Verify private output paths are ignored before saving real content
under backend/data/authoring_work/. Preserve originals and checkpoints.
Deliver exact artifact paths, versions, unresolved issues and review needs.
Schema-valid output and model agreement do not constitute approval.
```
