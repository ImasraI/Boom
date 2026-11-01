# Human and teacher tasks

Dated **2026-10-22**. This is a staged instruction pack, not an implementation or release approval. Start with [README.md](README.md); coordinate technical handoffs through [SOL_PROMPTS.md](SOL_PROMPTS.md). Work remains local and free. Preserve original PDFs, checkpoints, reviewed evidence and other contributors' work. Do not transfer files to a VM, push, deploy, purchase services or include credentials.

**First action today:** choose one complete exam and its possible answer PDF, then complete H0's source-pairing record. Mark uncertain matches explicitly. This gives Sol and reviewers one concrete, traceable example before expanding the collection.

## H0 — Identify sources and pair questions with answers

Classify each document as current textbook, official exam, reputable mock, answer booklet, compilation or unknown. Record filename, document SHA256, publisher where known, subject, grade/major, edition/year/session, printed numbering and PDF page references. Sol can provide hash extraction; do not manually invent identifiers.

Pair question and answer PDFs using matching exam identity, session/version, question counts and printed numbers. Check a few distributed questions, including numbering resets and combined sections. Preserve competing matches as unresolved; filenames alone do not establish a match. A printed answer is an **author-provided key**, not scientific verification.

**Handoff:** source manifest, proposed pairings, supporting page references and unresolved cases. Unknown facts stay null or explicitly unknown. Preserve originals and record corrections separately.

## H1 — Lock curriculum, sampling and holdouts

Confirm the actual textbook editions and allowed lessons for each product mode, including the reviewed next Maze scope for weekly ranked matches. Teachers resolve disputed mappings. Historical exams provide design examples; they do not expand today's curriculum.

An initial planning proposal is approximately **300 source questions and 10–15 supported families**, spread across mathematics, physics and chemistry. These numbers are neither approved scope nor universal quality thresholds. Select coverage by concepts, figures, representations, difficulty mechanisms and recurring errors; document important omissions.

Before prompt improvement, freeze development and final evaluation manifests. Hold out whole exams and appropriate families. Detect the same questions appearing in compilations, answer PDFs, translated copies and near-duplicate variants; assign related material consistently. Keep final holdout questions, keys and review feedback out of authoring examples. If a final case informs development, retire it into development and replenish the holdout. Give the evaluator controlled access separately.

**Handoff:** signed-off curriculum/scope revision, sample rationale, split manifest and duplicate exceptions.

## H2 — Separate visual transcription from scientific review

Use two review passes. A visual reviewer compares transcription directly with original page images: stem, options in printed order, equations, minus signs, exponents, units, diagram labels, continuation regions and printed key. They record exact corrections or uncertainty without silently repairing the source's science.

A subject teacher independently checks scientific validity, curriculum fit, sufficient givens, uniqueness of the answer, solution and figure consistency. A faithful transcription can still contain a source error. Record extraction status and scientific status independently, attached to the exact content revision. Model agreement never sets human-reviewed status. Use separate reviewers for transcription and blind solving, or have the same person solve before inspecting any answer-bearing source. The blind packet excludes answer pages, proposed keys, explanations and prior verdicts.

Copy this instruction to a teacher and print one rubric per item:

```text
Review the supplied anonymous item and original source regions, where relevant.
Record your reviewer ID, subject, date and exact item/version ID.
If doing both passes, perform the blind portion of Pass B before seeing any
answer-bearing source in Pass A. Request separate question and answer packets.

Pass A: compare the transcription with the image. Mark each field accurate,
incorrect or unreadable; give page/region references and literal corrections.
Do not reconstruct missing symbols from what you believe the question means.

Pass B: first solve without seeing the proposed answer, explanation or model
verdict. Record a short checkable derivation. Then inspect all options and the
key. Check curriculum, domains, units, sufficient givens, unique answer and
figure consistency. Distinguish source mistakes from extraction mistakes.

Rubric: for each dimension mark pass / defect / uncertain / not applicable.
Dimensions: transcription; curriculum; scientific correctness; unique answer;
wording; figure; distractors; cognitive demand; exam likeness; originality.
Explain defects with a specific counterexample or correction. Describe the
shortest solution and what reasoning is genuinely necessary. Do not equate
long arithmetic with difficulty or claim student-calibrated difficulty.

Finish with accept for the stated purpose / hold for correction / unresolved.
Record what evidence would resolve uncertainty. Do not approve unseen items.
```

## H3 — Compare generated questions with source questions blindly

Have Sol prepare randomized, anonymous packets with comparable subjects, scope, families and presentation. Hide generator identity, provider verdicts and generated-versus-source labels during initial judgment; reveal provenance afterward for source and novelty checks. Keep scoring rules fixed before reviewing results.

Routine H3 feedback uses development cases. Review final holdouts only after the candidate is frozen. If those results inform another improvement, move the affected cases into development and replace the final holdout before making a new evaluation claim.

Ask teachers for actionable feedback: missing constraint, shortcut, misleading distractor, unsupported concept, copied structure or required insight. Preserve independent judgments before adjudicating disagreements. Report counts, denominators, unresolved items and critical defects alongside ratings. Strong average exam likeness cannot compensate for wrong answers. Feed back reviewed corrections, never unreviewed model accusations.

## H4 — Run a controlled 20-student pilot

After teacher-cleared materials and Sol's readiness report, a proposed 20-student pilot can test comprehension, usability and obvious defects. It is not precise difficulty calibration, discrimination estimation or statistical proof of fairness.

Use minimal pseudonymous IDs, voluntary participation and age-appropriate consent. Keep identity mapping separate; avoid unnecessary names, school details and sensitive free text. Agree retention and access before collection. Record item version, response, elapsed time, interruptions and reported ambiguity. Report sample sizes and uncertainty, including missing responses. Keep experimental results separate from public ranked ratings.

If you want to contribute code, claim a bounded task from Sol's board: a synthetic fixture, a minimal reproduction of a student-visible bug, or an operator usability check. Use the same file ownership and handoff rules as Freebuff. Keep source/expert decisions explicit even when you also implement the tool that records them.

## H5 — Decide against an exact release candidate

After Sol's report, review remaining defects, holdout contamination, teacher evidence, scope, novelty, exposure fairness, observed limitations and rollback readiness. Record accept, limited pilot, hold or reject against the exact code revision, corpus snapshot and content hashes. Identify the prior approved snapshot and rollback owner. Approval of this plan does not authorize deployment; any later rollout needs the user's explicit instruction.

Copyable handoff form:

```text
Stage / date / owner:
Input document, item and content revision IDs:
Code revision / corpus snapshot:
Evidence files and page references:
Extraction status / scientific status / human reviewer:
Decision and allowed purpose:
Unresolved defects / exclusions / uncertainty:
Next owner and required evidence:
Release candidate / previous snapshot / rollback owner, if applicable:
```
