# Reasoning calibration proposals — pending review

24 October 2026. These proposals do not modify taxonomy0.1, source records,
question eligibility or student analytics. They arise during a small purposive
math-only development pilot and are not prevalence estimates for Konkur.

| Boundary needing calibration | Proposed decision | Synthetic illustration | Compatibility consequence |
| --- | --- | --- | --- |
| Algebraic restructuring vs substitution | Consider a new `tech.algebraic_restructuring` only if reviewers find existing substitution/representation tags misleading. Require identifying an identity/factorization that changes the solution, not ordinary simplification. | Recognize two cubic expressions as a cube of a sum/difference. | New ID requires approved taxonomy version and positive/negative examples; no automatic remap. |
| Routine limit evaluation vs limiting-case heuristic | Clarify whether `tech.limiting_cases` includes an explicitly requested one-sided limit, or is reserved for boundary tests used within another problem. | Compare a function tending to infinity with a boundary test used to reject a finite-parameter claim. | Definition change may require reannotation. Keep current pilot tags provisional. |
| Product rule vs repeated-unit counting | Determine whether independently constrained identical rows qualify as repeated-unit counting. Do not extend the label to arbitrary multiplication. | Three independent rows each have the same valid colouring count. | If a new counting label is needed, preserve old annotations and migrate explicitly. |
| Equation setup vs rewriting supplied equations | Setup requires a meaningful translation or reduction; copying a given equation is not setup. Representation-change may also be too broad for every algebraic reduction. | Turning event independence into probability constraints is setup; copying an existing polynomial is not. | Clarification first; add labels only with evidence. |

Reviewers should record accept/revise/reject/unresolved with a concrete example.
An agreement between two models is candidate evidence, not human adjudication.
No rare label should be removed merely because it is absent in fourteen items.
