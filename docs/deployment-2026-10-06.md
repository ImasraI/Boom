# Verified deployment — October 6, 2026

Initial application revision: `adf5631` (logo cleanup after feature commit `d8caeba`).
The feature commit uses the requested message:
`restructure: ranked ,UI frature: knowledge graph,themes`.

Both commits were pushed normally to `origin/main`. The Oracle checkout at
`/home/ubuntu/Boom` pulled with fast-forward and the `boom-backend` service
restarted successfully. Cloudflare Pages serves the new frontend; the live
shield bytes match the PNG committed to the repository. Only
`frontend/public/karzar-shield-detailed.png` is retained. Other generated
variants, `logo.png`, `logo-v2.png` and `favicon.png` were removed. The PNG is
stored directly in Git so deployment does not require Git LFS.

## Preservation and configuration

VM backups are at `/home/ubuntu/boom-backups/20261006T083317Z` (and an earlier
snapshot at `20261006T082904Z`). The environment file was saved with mode
0600, SQLite backed up through its backup API, and Chroma archived with its
writers stopped. Twelve accounts, previous exam snapshots and attempts,
wrong-answer records, OTP records, study sessions and the persistent JWT
secret were verified against the backup after deployment.

VM production preflight passed. Its existing compatible Gemini setup was
retained: `gemini-embedding-2`, 768 dimensions, 1,783 document chunks and
126 question chunks. Both active collections passed a real hosted query
probe and retained their embedding provenance. No laptop application
database, development auth settings or localhost proxy was uploaded.
Backend dependencies did not change; VM `pip check` passed.

## Verification

- Full local suite after the history correction: 431 backend tests passed, 3 skipped; 22 frontend tests
  passed. TypeScript, explicit Cloudflare production build, dependency
  consistency, changed-source/bundle secret-pattern scan and diff checks
  passed.
- Real public API: health JSON, CORS, authentication requirements, identity,
  calendar and curriculum graph passed for two existing users. Non-admin
  access to the question-review bank returned 403. Authenticated admin pool
  and corrupt-question endpoints passed.
- VM workflow checks used a separate temporary application database, with
  production configuration. Password login, practice reuse, hidden answer
  keys, account isolation, reports, quarantine, corrected revisions, ranked
  fresh-booklet preference/fallback and assessment filtering passed. These
  checks never inserted test users/questions into the production user DB.
- Actual VM OCR resources produced 480 minutes per day and 18 practice
  blocks with book names and printed question ranges. Manual and recurring
  activities survived, no overlaps were found, and another account's
  calendar stayed empty in the isolated workflow test.
- SMS.ir authentication and positive credit were verified through the
  deployed admin endpoint. OTP bypass is disabled. No SMS was sent; real
  carrier delivery time is not verified by a credit check.

## Remaining operational limits

The VM still has no processed page images. Figure/page-image retrieval
requires a separate upload to the corpus's referenced paths. Raw PDFs are
not required. Continuous pool runs have no storage ceiling, but provider
quotas and cancellations still stop generation. Verified reusable questions
avoid provider calls when enough eligible stock exists; an empty or
incompatible ranked bank still needs a working generation provider.
The deployed pool reports a terminal daily Gemini quota block with retry
time `2026-10-07T07:00:00Z` (October 7, 10:30 Tehran). Three standard booklets
are ready; no ready ranked booklet is currently available. No depleted
generation calls were retried during verification. The reusable-question
paths were exercised in isolated VM checks, not by inventing live stock.

Browser visual verification was previously denied and is not claimed here.
The live HTML, exact shield PNG and authenticated HTTP workflows were
verified. Unrelated local Pico monitoring work was preserved and excluded
from these deployment commits.

## Planner follow-up

The reported missing-practice warning had several causes. Generic OCR subject
headings were treated as chapter choices. An empty legacy OCR directory could
hide populated pages in the `.pdf` directory. Missing lesson headings prevented
matching even when a question's actual text contained the requested topic.
Some OCR pages contained placeholder options rather than real questions.

The planner now ignores generic headings when choosing chapters, merges the
two OCR layouts without counting a page twice, matches individual question
text when necessary without bridging unrelated questions, and excludes
placeholder-choice records from OCR and indexed-vector assignments. It loads
the student's saved exam provider, checks provider and grade, and binds mock
topics to their own date instead of combining separate exams. Each block
states its source; the UI distinguishes absent question metadata, exhausted
ranges and unfinished study prerequisites. Existing manual commitments and
accounts remain preserved.

The available shared corpus is incomplete. The only cached mock outline is
the summer 1405 schedule, with no upcoming exam in the audited period. Physics
has only ten usable numbered questions. These fixes cannot create missing book
content; current mock outlines and complete, accurate OCR remain necessary.
The image upload command copies `backend/data/1` into the same VM data path;
images alone do not supply missing numbered-question OCR.

Pico was never tracked or pushed, and the VM check found no Pico folder or
workflow. Both local paths are now explicitly ignored.

## History-dependent planner correction

The first clean-account workflow missed a production-history failure: an old
unverified booklet supplied unsupported topics, blank answers gave them maximum
weakness, and untouched generated proposals kept returning as overdue tasks.
The weekly planner now uses verified, non-quarantined mock evidence and avoids
double-counting generated mock mistakes. Untouched automatic proposals do not
become confirmed missed work. Explicitly missed/partially completed tasks and
manual commitments remain; no account or exam history is deleted.

The scheduler rebalances focus tasks before scheduling and tries another fitting
task when a short gap would strand a fifteen-minute fragment. This fixes the
45-minute-focus case around a protected manual activity. Seed chapter ranking
also favours recognisable headings over generic OCR labels. Calendar cells show
the printed test range and book separately, keep time ranges in chronological
order, and use more vertical space. Detailed notices are expandable.

Signup previously cached its preferences only in the browser. Signup, login and
boot now migrate a complete browser-only profile to an empty server profile,
using version checks and account-change guards. Existing server preferences win.
Resetting an account is unnecessary and would lose useful history.

The profile editor also uses the signup study goal for unset weekday sliders,
instead of silently proposing three hours on every day. Explicit daily overrides
and rest days remain intact. Saving a legacy profile without a global goal
stores its chosen daily-hours average as well as the individual day settings.

The candidate passed a VM test using a temporary SQLite backup of the actual
account history and the actual shared corpus, without modifying production
records. A four-hour goal with 45-minute focus blocks produced 16 numbered book
practice blocks (11 math, 4 chemistry, 1 physics), no generated fifteen-minute
fragments and no regenerated integral/Gibbs topics. The protected manual block
was retained. Remaining physics source exhaustion is a corpus limitation.
