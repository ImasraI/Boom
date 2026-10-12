# Weekly Maze ranked matches

Grade-12 math/physics ranked matches use ten independently verified, book-backed
questions from the next announced Maze exam: four math, three physics and three
chemistry. Math covers each branch listed in that exam. Student subject filters
are ignored. Other majors keep their existing shared-subject rules until their
reviewed schedules are supplied.

The admin generation section has a separate **کولوسئوم هفتگی · ماز** control.
Zero booklets means continuous generation. Drafting and verification use separate
workers. During a weekly run, older full-mock drafts remain saved but do not consume
its queue capacity or verifier priority. Missing or expired schedule data pauses
the run with an actionable message.

The schedule is reviewed data in `backend/data/cache/mock_schedules/*.json`, not
model memory. Version 1 records the provider, major, grade, source PDF SHA-256,
review status, Jalali dates, per-book school years, topics and exact scope quotes.
Changed PDFs require re-extraction and review. If the original PDF is absent on
the VM, deploy the reviewed processed resource through the trusted admin workflow.
Chapter mapping and OCR passages must also be available; no unrelated chapter is
substituted. Updating dates, topics, chapter IDs or boundary quotes changes the
scope fingerprint and excludes old stock from new ranked matches.

`ARENA_WEEKLY_MAZE_ENABLED=True` is the default; `POOL_DRAFT_QUEUE_ENABLED=True`
is required for weekly generation. Ranked joins consume ready scoped stock and
never create a live-generation loading placeholder. Reused verified questions
remain eligible within the current scope when fresh stock is unavailable.

For twenty simultaneous students, prepare at least ten distinct ready papers
(one hundred questions) for one round, or twenty papers for two rounds. The admin
preview reports current-scope fresh papers and players supported for one round.
Before the event, check account access/OTP, grade and major profiles, paper stock,
mobile rendering and match submission. A passing health endpoint is insufficient.
