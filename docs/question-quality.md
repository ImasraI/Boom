# Question quality and model evaluation

Mock drafting and checking always use high reasoning effort where supported.
Each request handles one question, with at least 8192 completion tokens and a
300-second timeout. JSON output is explicitly requested. Gemini truncated JSON
is retried with a larger budget (up to 65536) without reducing reasoning effort.
These tokens include hidden reasoning; the budget is not a
promise that every request uses all of it. Chat/planning retain their separate
settings. Provider quotas are respected; keys do not increase a project's quota.

A draft must pass an independent blind solve and a separate audit of its key,
solution, options, units, givens, visible diagram and book scope. Equivalent
numeric choices and missing figures fail. A malformed reviewer reply, quota
failure, uncertain audit, or solver/auditor disagreement stays pending for retry.
Only explicit, explained defects are rejected. Decisions and reasons are saved
in the question JSON's `validation` field; old rejected questions do not acquire
invented reasons. This is a stronger gate, not a guarantee of mathematical truth.

Option order is preserved so explanations referring to an option cannot become
wrong through answer balancing. Completed drafts and review decisions survive
worker restarts. Repeated inconclusive reviews back off instead of repeatedly
spending quota. A definitive rejection is not silently given a different key.

## Human comparison

From `backend/`, run:

```bash
python scripts/compare_mock_models.py --run quality-20
```

This writes only ignored `data/model_evaluations/quality-20/state.json`; it never
publishes questions or writes bank stock. The two currently configured mock
models (Groq GPT-OSS 120B and Gemini Flash) get identical saved book excerpts,
topics, high reasoning and hard difficulty: 7 math (2 geometry, 1 statistics,
1 discrete, 3 calculus), 7 physics and 6 chemistry. Same-provider credential
failover (including the configured Gemini reviewer fleet) is allowed,
cross-provider substitution is not. A private quota ledger is initialized from
the API's saved blocks, so this background process cannot overwrite newer API
quota state. Every first parseable
draft is retained, including flawed ones, for an honest human comparison.

The checkpoint resumes without regenerating completed slots and honors saved
daily/minute/access blocks. `--once` exits on provider unavailability instead of
waiting. The progress file includes counts, model identities and statuses,
never credentials. A PID lock prevents duplicate evaluation workers.

After copying the private checkpoint to the laptop, from `frontend/`:

```bash
node scripts/export-model-comparison.mjs /absolute/path/state.json /absolute/path/output
```

The export separates questions from answer keys and renders math and figures.
Rate correctness, sufficient givens, exactly one correct option, explanation
accuracy, book/topic fidelity, appropriate difficulty and visible diagram quality.
Review all 20 samples before choosing a model; do not compare only accepted ones.

The laptop can keep the private review sheets updated while the VM runs:

```bash
python backend/scripts/watch_model_comparison.py --host USER@VM --key /path/to/existing/key
```

It makes no model calls, exports only to the ignored `tmp/` directory, and stops
when both sets finish. HTTP 503/provider failures use saved exponential backoff,
up to 15 minutes. Unchanged states stay quiet. A lost SSH connection cannot
reset generation; rerun the copying command to resume downloading the results.
