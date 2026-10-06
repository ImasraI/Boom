# Production reports: question bank, mock reuse, planning and chat formatting

Deployment completed on October 6. See the
[verified deployment report](deployment-2026-10-06.md). The restriction and
resume notes below describe the earlier blocked session, now resolved.

## Local changes ready for review

- The detailed Persian shield is installed on the landing page, login,
  application header, favicon and touch icon. The site name remains Boom.
- Admin generation selects mock/ranked/both, major, difficulty and grade.
  A positive count means that many new booklets; zero runs continuously
  until cancellation, provider refusal or generation failure. Previous
  inventory does not cap this run, and there is no bank storage ceiling.
  Automatic startup top-ups retain their configured small budget and minimum
  stock targets; those targets do not limit admin generation or storage.
- Practice prefers already-used eligible questions, including the student's
  own private questions. If only a smaller used set is available, it shows
  the actual count and duration instead of inventing questions. Ranked
  prefers unused shared booklets/questions, then assembles a reusable shared
  set. Questions from another student's private uploads cannot enter it.
  Both paths still require compatible subject/grade/topic/difficulty and
  verified answers. Insufficient eligible ranked stock still requires live
  generation and therefore a working provider.
- Questions have their own persistent records, independent of exam
  snapshots. Verified survivors from incomplete generation are retained.
  Existing shared pending stock and the current student's own older mocks
  are indexed lazily. Old claimed private exams are never guessed to be
  shared merely because of their title.
- Each mock, arena and built-in assessment question can be reported through
  its authenticated source exam. Reporting quarantines that individual
  question from future selections and serving, retaining its siblings,
  original exam snapshot and report evidence. Admins can inspect reports,
  save notes, restore valid questions, exclude them permanently or create
  a manually reviewed corrected revision. Deleted/corrected originals stay
  visible in the archive. Corrections do not rewrite historical attempts.
- A ranked match affected by quarantine is cancelled without Elo changes
  at submission rather than scoring players against different question sets.
- Built-in assessments use the authored source at
  `frontend/src/assessmentQuestions.json` through the backend report bank;
  ship this tracked source file with the full backend checkout. Assessment
  questions do not enter ranked selection.
- A failed mock request now displays its error on the configuration screen.
  The screen stays mounted so difficulty, count and topics survive failure.
  It sends the signed-in student's grade and major, and its back button
  navigates home instead of leaving the site through browser history.
- A terminal Gemini daily generation quota is remembered across new client
  instances in the API process. New live generation stops before making more
  known-depleted calls. Existing verified pool stock can still be claimed.
  Admin status displays a readable error and next retry time. A restart clears
  this process-local memory; a subsequent actual provider refusal restores it.
  Without system IANA timezone data, the UTC-8 reset fallback deliberately
  waits conservatively rather than retrying early during daylight saving.
- Subject generation and replacement verification stop on terminal daily
  exhaustion. Unverified or incomplete booklets still fail closed. Failed
  requests refund the student's reserved generation allowance.
- Admin restock refuses a concurrent start while automatic pool generation
  already owns the progress record.
- The planner discovers numbered questions from promoted shared OCR JSON
  even when the VM has neither raw PDFs nor populated book catalogue rows.
  It uses actual contiguous printed question numbers, excludes known
  ineligible raw books, respects inferred grade and explicit science track,
  and supports OCR folder names with a `.pdf` suffix.
- Chat converts plain `<br>` tags into line breaks, including table cells.
  Arbitrary HTML stays escaped; code examples preserve their literal tags.

## Validation

- The latest deployment-readiness run passed 413 backend tests, 3 skipped,
  including regressions for private AI practice and releasing a failed
  worker's slot. Two existing full-suite skips plus one IANA
  timezone integration skip on this Windows installation; the conservative
  missing-timezone behavior is tested separately.
- 14 frontend progress tests and 5 real chat render tests passed.
- TypeScript passed. Production Vite build passed with the native config
  loader, avoiding the sandbox-blocked configuration bundler subprocess.
- An explicit Cloudflare Pages production build with
  `VITE_API_URL=https://api.boomedu.ir` also passed. The resulting shell has
  all six referenced local assets, the shield and `_headers`; its JS bundle
  contains the correct API origin. These checks do not publish the build.
- `pip check` and `git diff --check` passed. A scan of 34 changed/untracked
  source files and the built JS/HTML/CSS found no matching private-key or
  supported API-key patterns. This is a limited pattern scan, not a claim
  of comprehensive security auditing.
- Backend tests used fresh workspace scratch directories with inherited
  Windows permissions. Standard temporary directories on this host have
  restrictive ACLs; the application/user databases were not used for tests.
  Chroma held some scratch files open until process exit; these remain only
  in the ignored `tmp/verification` directory.
- Live browser verification was denied by the browser permission policy.
  No visual approval or authenticated production smoke test is claimed.

## Deployment and provider limitations

Update, October 6: the earlier sandbox restriction was lifted. Git fetch and
VM SSH now work. Production preflight passed on the VM with 12 accounts and
both complete Gemini collections (1,783 document chunks and 126 question
chunks). The reviewed release is being deployed after VM data backups. Only
the detailed shield logo is retained; other logo variants are removed.

The read-only laptop preflight found both compatible 768-dimensional Gemini
text collections, intact local database checks and 17,777 processed page
image files. The status viewer reports migration complete: 1,909/1,909
stored chunks, zero remaining. Local production configuration validation failed on APP_ENV,
development auth settings and CORS. This laptop configuration is not a VM
production `.env`; do not copy it wholesale to the VM. Local image presence
does not verify that the VM has the images referenced by its corpus.

These changes are local and have not been pushed or deployed. This session
has read-only Git metadata and its SSH entry point is explicitly blocked.
The actual fetch failed with `.git/FETCH_HEAD: Permission denied`.
`ssh` resolves to the sandbox denial wrapper, not an authenticated remote
session. Browser access to the isolated local verification page was also
denied. Do not work around any of these restrictions using alternate Git
metadata, SSH implementations or browser surfaces.
Do not interpret that restriction as an Oracle VM outage. VM logs and
authenticated production workflows were not verified in this follow-up.

The admin's reported `GenerateRequestsPerDayPerProjectPerModel-FreeTier`
failure means the provider's daily generation allowance is exhausted.
Local error handling cannot restore provider capacity. Wait for its reset,
enable appropriate billing, or explicitly configure a valid separate pool
provider and key. Keys from the same project do not provide independent
project quotas. Google documents project-scoped limits and midnight Pacific
daily resets in its [rate limit guide](https://ai.google.dev/gemini-api/docs/rate-limits).
Do not silently switch pool generation onto the chat budget.

During a later authorized deployment, preserve the VM database, accounts,
private uploads and persistent JWT secret. Back up with the SQLite backup API,
stop vector writers before backing up Chroma, deploy a reviewed revision with
fast-forward Git operations, and retain the existing compatible Gemini text
vectors. Do not upload the laptop database or localhost proxy configuration.

Numbered OCR is still incomplete for many books. Plain OCR prose cannot
justify invented test ranges. After structured question OCR is promoted,
regenerate the relevant week to receive concrete book/range assignments.
Existing plans are not silently rewritten by this change. Page images remain
a separate upload. Long live-generation requests may still hit an upstream
timeout; no asynchronous mock-generation job was introduced here.

## Resume deployment after the session has Git-write and SSH access

1. Review the working tree, fetch remote changes and preserve unrelated work.
   Commit with the authorized exact message:
   `restructure: ranked ,UI frature: knowledge graph,themes`.
   Push normally; do not force-push or replace remote history.
2. Connect as `ubuntu@158.179.207.226` using the existing local key at
   `C:/Users/Arsam/Downloads/ssh-key-2026-09-18.key`. The checkout is
   `/home/ubuntu/Boom`. Identify the actual running services and deployed
   revision before stopping writers or changing anything.
3. Back up the VM `.env`, application SQLite using its backup API and Chroma
   with writers stopped. Retain accounts, private uploads, JWT secret,
   compatible shared Gemini vectors and provider credentials. Do not copy
   the laptop's application database, localhost proxy or whole `.env`.
4. Fast-forward pull the pushed revision; install only required dependencies
   and restart the actual backend services from `backend/`. `ensure_schema`
   creates the bank tables and backfills flags on the existing database.
   The old-schema upgrade is tested without replacing accounts or mocks.
5. Confirm Cloudflare builds the same revision with the correct API origin.
   Verify boomedu.ir beyond health200: login, distinct-account isolation,
   weekly planning, chat line breaks, assessment reporting, admin quarantine
   review, practice reuse and ranked fresh/fallback ordering. Stop any
   explicitly started continuous generation run after the smoke test.
   Do not send an OTP to an unapproved recipient or repeatedly probe a known
   depleted provider. Record the real revision and remaining failures.

Page-image upload and provider capacity remain separate operational
requirements. This change does not grant unlimited Gemini requests.
