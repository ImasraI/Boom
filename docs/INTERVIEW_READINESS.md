# Interview readiness - 31 October 2026

## Start the prepared local demonstration

From the repository root on the prepared laptop:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/run_interview.py
```

- Frontend: http://127.0.0.1:8443
- API documentation: http://127.0.0.1:8000/docs
- Private API-check account: `backend/data/interview-readiness/account.private.json`
- Local UI login: `backend/data/interview-readiness/demo-login.private.json`
- Local reports and logs: ignored `tmp/interview-readiness/` and `backend/data/interview-readiness/`.

The interview backend is an ignored snapshot of the deployed revision, prepared
under `tmp/interview-readiness/release/backend`. It uses an independent SQLite
database populated with an authorized export of shared stock. Production accounts,
password hashes, private conversations and student progress were not imported.
The frontend uses the current working tree through its normal local API proxy.

The main working tree contains experimental source-policy and authoring work.
Its reviewed-policy manifest currently has no eligible records. Do not describe
that empty experimental route as the deployed retrieval implementation. The demo
snapshot keeps that experiment separate from the currently deployed backend.

The local demo disables optional reranking because the reranker weights were not
fully cached. It also disables automatic bulk ingestion and pool workers. Missing
optional image models fail promptly in offline model-loading mode; text and
linked page evidence can still be used. Do not claim the local demo benchmarks
the deployed reranker. Actual API calls still require network access.

Provider requests on this laptop use a private SSH SOCKS tunnel configured in an
ignored file; the launcher can restart it using the existing SSH identity. The
virtual environment includes `socksio`. Credentials stay in ignored environment
files; no API key belongs in frontend settings, documentation or Git. Original
local environment and access-ledger snapshots were preserved before updates.
Daily quota records were retained. Stale access denials were removed only after
successful authentication through the repaired network route.

## Reproduce HTTP checks

Run this from the prepared snapshot's backend directory, using the repository's
virtual-environment Python and its copied `scripts/interview_smoke.py`:

```text
python scripts/interview_smoke.py --chat --mock
```

`--provision` creates a dedicated non-admin test account when first preparing an
environment. No SMS is sent. The check exercises password login, identity,
profile onboarding, weekly scheduling, saved calendar, ranked filters, cited
chat, and a three-question stock-backed practice test. `--full-mock` explicitly
tests the stricter 105-question format; it currently reports unavailable stock.
The generated-booklet response contains an ID/count; the script then fetches
the actual questions using that ID. HTTP 200 alone is insufficient validation.

## Verified and incomplete work

- Baseline checks: 1,421 backend tests passed, three skipped; 105 frontend tests
  passed; TypeScript and the production frontend build passed.
- The isolated staged release passed 996 backend tests, three skipped. Focused
  policy/source-score/planner regressions passed 34 tests. The frontend's 105
  tests also passed again after the package rename.
- A real dedicated deployed account completed profile setup, a 37-block weekly
  plan and calendar persistence, greeting/cited chat, and a three-question
  practice test. These checks used real HTTP requests and existing providers.
- SMS-provider authentication and positive credit were checked without sending
  a real verification message. SMS delivery and a complete phone-signup flow
  were not exercised.
- The local isolated database received 1,891 shared active verified bank
  records and 144 unclaimed shared papers. Verification flags are existing
  system records, not a new claim of human or scientific review. The import
  was repeated to confirm that the identical export did not create duplicates.
- The local frontend was opened in a browser using the dedicated account; no
  JavaScript errors or failed API responses were observed during the check.
- The final real local HTTP run passed all core smoke checks. Cited chat returned
  16 sources in 33.67 seconds for the selected derivative question. This single
  run is a functionality observation, not a latency or accuracy benchmark.
- Production received three additional ten-question practice booklets assembled
  from existing verified stock. A bounded five-minute queue run verified three
  additional saved questions. It did not produce a complete full mock. Pending
  jobs and quota state were retained when the bounded run stopped.
- **Full 105-question mocks remain unavailable:** the existing bank does not
  provide sufficient source-grounded branch/topic diversity. Old pending paper
  counts do not establish eligibility for the full format. The existing 409
  response correctly distinguishes full mocks from short practice tests.
- **The upcoming ranked scope remains incomplete:** two trigonometry mappings
  are absent from its curriculum coverage. Existing verified stock can support
  the prior reviewed scope, with the existing explicit fallback notice. No
  curriculum mapping, review receipt or verification flag was fabricated.

## Code corrections in this change

- Answer-source construction accepts both policy `score` and legacy
  `hybrid_score` records and preserves a legitimate zero score. A regression
  test drives a policy result through actual answer-source construction.
- Removed the unused weekly LLM prompt; the weekly endpoint uses the
  deterministic planner. Retained helpers referenced by existing tests and
  the unfinished authoring work.
- Renamed the frontend package from its scaffold name to
  `boom-study-companion`, including lockfile metadata.
- Corrected reranker comments that asserted Persian quality, CPU placement and
  latency without supporting measurements in the code.
- Added a real HTTP smoke runner, shared-stock importer and local demo launcher.

This is a bounded readiness assessment, not a claim that every feature, subject,
difficulty, concurrent-load condition or third-party delivery route was tested.
