# Karzar question-authoring roadmap

User-approved direction, 13 October 2026. Recommendations below are not all
implemented. Use the local import handoff to distinguish working features from
future work. The current user instruction prohibits VM work and pushing until
the user explicitly asks after reviewing standardized data.

## What the brain means

API keys authenticate requests; they neither learn nor retain a private brain.
Store the shared authoring system in the application: curriculum evidence,
exam-design records, retrieval, validated problem specifications, evaluation,
and reviewed feedback. All providers use that same versioned system.

Keep three evidence roles separate:

1. Textbooks establish allowed concepts, terminology, facts and prerequisites.
2. Official exams and reputable mocks establish observed question-writing
   patterns, representations, cognitive demands and distractor strategies.
3. Mathematical checks, independent solving and expert review establish
   correctness of newly generated questions.

An uploaded old exam must not silently expand the present curriculum or the
next Maze scope. A real exam can include older syllabus topics. An inferred
design strategy is not evidence of its author's private thoughts.

## Priorities and deliverables

| Priority | Improvement | Concrete deliverable |
| --- | --- | --- |
| P0 | Reliable imports | Hash-identified documents, page coordinates, original crops, literal transcriptions, separate uncertainty and answer provenance |
| P0 | Understand exam design | Question-level records describing tested skills, representations, observable solution strategies, meaningful distractors and difficulty mechanisms |
| P0 | Correctness before volume | Build supported problem families from checked parameters; derive an answer before wording/options; preserve blind solve and audit |
| P1 | Better independent evidence | Solver first derives a final answer without options/key; map it to exactly one option; retain short checkable calculation evidence |
| P1 | Scientific figures | One declarative problem specification drives SVG figures, givens, units and validators; extend graphs/geometry to circuits, vectors and free-body diagrams |
| P1 | Useful defect feedback | Separate wrong key, ambiguity, insufficient givens, equivalent options, bad explanation, bad figure, OCR defects, curriculum mismatch, uncertainty and provider failures |
| P1 | Real difficulty | Define cognitive steps, concept combinations, case distinctions and representation changes; calibrate against accuracy and response time |
| P1 | Fair matches | Prefer questions unseen by both players; retain per-question-version exposure, not just global booklet usage |
| P2 | Precise learning support | Mistake-specific remediation rather than only broad topic weaknesses; keep accuracy colours but show sample size and uncertainty |
| P2 | Measurable operations | Coverage by scope/topic/family/difficulty, actual tokens per accepted question, waiting reason, queue age and reviewed-error rate |
| P2 | Fine-tuning | Consider only after a clean reviewed dataset and held-out evaluation demonstrate a remaining style/adherence problem |

## Design example

An exam item testing velocity-time graphs may combine signed area, displacement
versus distance, and an interval containing a sign change. Record those skills
and the mistakes that produce plausible options. Generate a different graph,
question task and inference combination. Do not simply copy the stem, swap
numbers or duplicate its complete condition/distractor structure.

Require source-supported concepts while allowing newly constructed numerical
parameters. Record which quantities are quoted facts and which are generated
and checked. The current prompt's reference to source numbers should not make
every new parameter depend on appearing verbatim in a book.

## Correctness and review

Preserve the existing independent blind solve, audit and quarantine. Add exact
checks for supported families: domains, equivalent expressions/options, units,
chemical balance, geometric consistency and graph constraints. Numerical
sampling alone is not proof. Unsupported or inconclusive cases remain pending.

The reviewer must judge scientific validity separately from extraction quality.
A malformed provider reply or exhausted quota is not a bad question. Do not
raise acceptance by weakening the quality gate. Teacher review targets model
disagreements, new families and a random sample of accepted items.

Store reviewed counterexamples and corrections. Do not teach the system an
unreviewed model accusation. Preserve question versions, invalidation reasons
and the valid questions from affected booklets.

## Difficulty and the product

The four requested levels are easy, konkur, hard and extreme. Extreme means
deeper reasoning within the same curriculum, never university material. Measure
intended versus observed difficulty, time and discrimination after enough
responses. Suspiciously difficult items need ambiguity/key review.

Keep the current math-physics full-paper blueprint: 40 mathematics, 35 physics,
30 chemistry, with the user's branch counts. Weekly ranked uses the reviewed
next Maze scope; source imports must not change that rule.

Support remediation such as degree/radian confusion, sign errors or missing
domain restrictions. A repeated error can trigger one short explanation, one
guided example and two independent attempts in a relevant planner session.
Homework insertion should expose which generated session it replaces and why.

## Credentials and credibility

Separate generation/verification roles without claiming independent provider
capacity. Groq quotas belong to organizations; Gemini quotas belong to projects.
Record group membership only with explicit owner evidence, never from key count
or similar quota errors. Expose masked identifiers and health, not credentials.

Question review records should show sources, curriculum tags, model/prompt
version, checks, figure provenance and human review when it actually occurred.
Do not describe model agreement as human verification or absolute truth.

## Evaluation before training

Start with approximately 100 representative pages and 300 reviewed official
questions across math, physics and chemistry. Keep entire exams/families out of
the application example bank for evaluation. Compare current generation with
design-record conditioning using blind teacher review. Twenty samples per model
are useful for an initial comparison, not reliable error-rate calibration.

Track accepted-item correctness, curriculum/scope fidelity, unique answer rate,
figure fidelity, novelty, design diversity, human-rated exam likeness, extraction
critical-error rate, latency and actual total tokens per accepted question.

Fine-tuning may improve style and structured adherence; it does not replace RAG
or validators. Google currently documents ordinary Gemini API/AI Studio tuning
as unavailable, with cloud-platform tuning available instead. Recheck provider
support, models, cost and dataset requirements before implementing training.

## References checked on 13 October 2026

- [PaddleOCR structured parsing](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PP-StructureV3.html)
- [Marker and model licensing](https://github.com/datalab-to/marker)
- [Gemini document processing](https://ai.google.dev/gemini-api/docs/document-processing)
- [Gemini tuning availability](https://ai.google.dev/gemini-api/docs/model-tuning)
- [SymPy solvers](https://docs.sympy.org/latest/modules/solvers/solvers.html)
- [Groq quota scope](https://console.groq.com/docs/rate-limits)
- [Gemini quota scope](https://ai.google.dev/gemini-api/docs/rate-limits)
