# Three-question decision/distractor pilot

Prepared locally after the G01–G06 editorial feedback. This is an additive
experiment, not a rewrite of the six questions or a production release.

## Frozen plan

Protocol digest: `0e82122d5cc4be4b05b71ced72451d3afe49aeda7297399d4ba046da5a615ead`.
Private root: `backend/data/authoring_work/decision-authoring-pilot-v1/`.
The generic factual briefs and source-image/OCR hashes come from the existing
geometry pilot. The six-item owner feedback receipt is bound to this new plan.
No held-out exam, raw source question, credentials or student data is supplied.

| Brief | Consequential decision | Construction excluded from this trial |
| --- | --- | --- |
| Cyclic feasibility | Combine a cyclic constraint and independent condition; reject an inadmissible angle branch | Previous isosceles trapezoid/diagonal-angle/bisector chain; one complement calculation |
| Cosine-law branches | Select a geometrically admissible algebraic branch and prove existence/uniqueness | Previous fixed60-degree/opposite-side perimeter range; only one positive option |
| Altitude/shape feasibility | Use common area and reciprocal-altitude relationships with an additional nonredundant constraint | Previous count of integer third heights from two fixed heights |

Hypothesized wrong routes and shortcut attacks are predeclared in each brief.
There is no assigned empirical difficulty or claim about what most students miss.

## Compatible records and independent evaluation

The response envelope has `candidate` and `audit_proposals`. Candidate retains
the existing pedagogical v0.2 schema. Sidecars propose three wrong-option traces,
shortcut analyses, an optional fast route and a figure-fidelity plan. The validator
checks coverage, exact option references, bounded fields and step references.
It cannot establish that an error trace is mathematically plausible/correct.

Separate independent packets contain (a) the written stem with no options and
(b) the stem with options. Neither receives the author key, solution, design,
sidecar hypotheses, private profile or the other solver's response. A stem-only
answer remains a free response pending semantic checking; no string equality is
silently promoted to mathematical agreement. No figure is supplied, so the option
audit cannot claim image measurement. Diagram attacks require separate visual work.

Evaluation instructions are frozen separately in `evaluation-policy-*.json`;
per-candidate packets are created only after a structured draft exists. Optional
fast routes remain proposals, not verified techniques or measured speedups.

Figure screening measures short segments under the current SVG projection at
320px and480px. The provisional18px threshold is a usability flag, not scientific
or visual approval. It does not cover all label collisions/apparent tangencies.
It never moves points or changes mathematical relations automatically.

## Actual execution status

The bounded runner was invoked once. Its credential-free transport check returned
ConnectError before a generation request: **0 attempted questions, 3 pending**.
`run-status.json` records `waiting_network` with `credentials_sent=false`.
No key quotas were reset or deliberately probed. The user has been asked to repair
the VPN HTTP proxy on port10809. Do not repeat requests until the connection changes.

The plan has a self-review of likely failure modes; a separate Astra architecture
review has NOT occurred. Do not invent that gate or its approval.

Actual validation: **175 focused tests passed**, including the new envelope,
sidecar, option-free projection, malformed-response preservation and option-audit
tests, plus the previous pedagogical/benchmark/figure/originality regressions.
The local TCP listener check also found no listener on10809 at this checkpoint.

## Resume commands (PowerShell, backend directory)

```powershell
Set-Location 'C:\Users\Arsam\Desktop\Boom-merged\backend'
.venv/Scripts/python.exe -X utf8 scripts/run_decision_pilot.py --max-items 1
.venv/Scripts/python.exe -X utf8 scripts/prepare_decision_verifiers.py
```

The runner preserves terminal outcomes, completed raw responses and quota/access
state. After the first draft, inspect mathematics and the claimed wrong routes
before running the other untouched items. Never overwrite a held response to make
it count as successful output. The verifier preparation does not execute calls.

Next Sol work after network recovery: generate at most one first, inspect its
key/options/full proof/distractor traces, then continue untouched items if suitable.
Run independent stem-only and option-aware checks; keep provider failures and
semantic disagreements. Build a new versioned human review only after those checks.
The user does not need to repeat G01–G06. No deployment, source promotion or VM work.
