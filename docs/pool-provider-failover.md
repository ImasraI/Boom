# Mock pool credentials and free capacity

## Independent drafting and answer checks

The deployed configuration uses Groq `openai/gpt-oss-120b` to draft questions
and replacements, with Gemini independently solving them. Chat and planning
keep their existing Groq settings; OCR/vision and retrieval keep Gemini.
Only independently accepted questions enter the reusable question bank.
The verifier receives diagram data, but never the draft's answer or explanation.
References to missing figures/tables cannot be certified by a guessed answer;
they require a replacement. The solver also rejects ambiguous or incomplete
questions rather than choosing the closest option.

Configure these roles in ignored `backend/.env`:

```dotenv
POOL_LLM_PROVIDER=groq
POOL_LLM_API_KEY=<existing Groq key>
POOL_LLM_MODEL_NAME=openai/gpt-oss-120b
POOL_LLM_FALLBACK_PROVIDERS=
POOL_VERIFY_LLM_PROVIDER=gemini
POOL_VERIFY_LLM_API_KEY=<existing Gemini key>
POOL_VERIFY_LLM_MODEL_NAME=gemini-3.6-flash
POOL_VERIFY_GEMINI_API_KEYS=<optional ordered Gemini backup keys>
POOL_VERIFY_MAX_TOKENS=2400
POOL_VERIFY_REASONING_EFFORT=low
POOL_GENERATION_BATCH_SIZE=4
POOL_GENERATION_MAX_TOKENS=2400
POOL_GENERATION_CONTEXT_CHARS=1800
POOL_GENERATION_REQUESTS_PER_MINUTE=1
POOL_WORKER_INPROCESS=False
```

Four-question drafts and one new draft request per minute provide a conservative
starting budget for Groq's free token allowance while chat shares its organization.
Actual capacity also depends on input/output size and other traffic. Existing
provider retries respect transient rate limits and Retry-After. Pacing is shared
among pool clients in one backend process; separate processes/organizations have
their own scheduler and provider-enforced limits.

Start a selected mock type from Admin; automatic restock stays disabled.
This configuration takes longer for a full booklet than for a short practice.
Stored, verified questions remain reusable without generation calls. If every
Gemini verifier key is known exhausted, new generation stops before drafting
spends Groq tokens. It never falls back to Groq verifying its own drafts.
An empty `POOL_VERIFY_LLM_PROVIDER` preserves the legacy single-provider behavior.

The browser starts `/api/mocks/generation` and polls its account-scoped job.
Long drafting no longer holds a Cloudflare request open. Repeated starts reuse
the same active job; leaving the page stops polling without cancelling generation.
Completed booklets persist in SQLite. Transient job status expires after two hours
and resets on a backend restart; an interrupted job must be requested again.
The synchronous `/api/mocks/generate` endpoint remains for existing API clients.

## Gemini credential failover

Admins can add credentials from **کلیدهای سرویس ساخت آزمون** in the Admin panel.
Choose Groq drafting, Gemini answer verification, or Gemini drafting. The form
appends to the corresponding private `backend/.env` backup list; it does not
switch providers/models or change chat, planning, OCR, or embedding credentials.
Inactive roles are identified in the panel and require server configuration
before use. Existing keys are never displayed or returned by the API.

`GET /api/admin/pool/credentials` exposes counts and remembered quota/access
status only. `POST` accepts `{provider, stage, key}` with admin authentication.
Duplicate additions are harmless. Writes are atomic and locked, and new pool
clients pick up the keys without a restart. A waiting selected run is awakened
to recheck availability; its selection and existing quota blocks are preserved.
Status is based on observed errors, not a new provider validation request.

Pool generation supports explicitly configured Gemini backup credentials.
Set `POOL_LLM_PROVIDER=gemini`, keep the primary key in `POOL_LLM_API_KEY`,
and add ordered backup keys to the comma-separated `POOL_GEMINI_API_KEYS`
setting in **ignored** `backend/.env`. Restart the backend and any separate
pool worker after changing environment settings. Never put keys in frontend
settings, Git, logs or public health responses.

The client stays with a working credential. A terminal daily refusal blocks
that credential/model until the next Pacific midnight and advances to the next
configured credential. `POOL_QUOTA_STATE_PATH` persists only hashed identities
and reset timestamps across restarts. Known exhausted credentials are skipped
without another API request. If every Gemini credential is blocked and no
usable alternative provider is configured, restock/live generation returns a
readable HTTP 503 with the earliest reset time; verified stock remains usable.
The independent verifier uses `POOL_VERIFY_GEMINI_API_KEYS` rather than the
drafting role's `POOL_GEMINI_API_KEYS`, preserving the same persisted cooldowns.
HTTP 401/403 also advances to an explicitly configured backup. Rejected
credential/model identities persist without their secret values and are skipped
after restart; they have no daily retry timer. Configure a valid replacement, or
clear the saved access rejection after resolving access for that same credential.
If every verifier credential is rejected, Admin and live generation return a
readable HTTP 503 before spending Groq tokens; verified stock stays usable.
Per-minute limits keep bounded retries and `Retry-After` backoff. Timeouts,
malformed answers and temporary limits do not silently switch credentials.

Google's quota scope is the **project**, not the account or API key. Additional
keys from one project do not add capacity. Independent, authorized projects
may have independently available allowances. This feature is availability
failover, not unlimited generation; do not create account fleets to circumvent
documented provider limits. See [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
and [Google API terms](https://developers.google.com/terms/).

`POOL_LLM_FALLBACK_PROVIDERS` also supports explicit provider alternatives,
such as `groq`. Each uses its configured provider key/model. Configure this
deliberately: reusing the chat provider's key also consumes its allowance.
Missing credentials, duplicate Gemini entries and unknown provider names
do not make a blocked pool appear available.

## Free options checked on October 7, 2026

| Option | Published allowance / limitation | Fit for this project |
| --- | --- | --- |
| [Groq](https://console.groq.com/docs/rate-limits) | Free `openai/gpt-oss-120b`: 30 requests/minute, 1,000/day, 8,000 tokens/minute, 200,000 tokens/day; organization-wide, dashboard values may differ | Already integrated. Large prompts plus output must fit the small token-per-minute budget; tune subject batches before enabling production fallback. |
| [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/platform/pricing/) | 10,000 neurons/day on eligible models; daily reset at 00:00 UTC. Neurons measure compute, not requests; some frontier models require paid billing. | Independent limited free allowance; needs a backend adapter/credential and quality checks. |
| Offline laptop generation/import | No hosted API allowance; hardware and electricity costs remain | Generate in advance or import real book questions and answer keys, validate, then upload to the existing question bank. The VM can serve/reuse verified questions without generation calls. |
| [Cerebras](https://inference-docs.cerebras.ai/support/rate-limits) | No permanent free tier: $5 trial credits expire after 30 days and require a verified payment method | Already integrated, but not a continuing free capacity source. |

Prefer growing and reusing the verified question bank over generating a new
booklet for every learner. Generation already verifies questions in batches of
ten. Preserve independent answer checks and report quarantine; changing keys
must never make unverified or reported questions eligible for practice/ranked.
