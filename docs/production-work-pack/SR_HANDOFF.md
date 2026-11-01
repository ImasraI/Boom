# SR — local review integration

23 October 2026. Contract: S0/ST 0.1 with the additive SR evidence-token extension below. Integration implemented; H2 human judgments remain pending. No deployment, provider requests, scanning, embedding, corpus promotion or real human decisions were performed.

## Changed integration surfaces

- `backend/app/rag/authoring_review.py`: private append-only decision, blind-solution and answer-exposure ledger. Each dimension is independent. Conflicting judgments are retained; no bulk approval, supersession or eligibility endpoint is provided.
- `backend/app/routers/authoring_review.py`, `backend/app/main.py`: existing admin authentication gates every packet, image and write. Reviewer identity comes from the authenticated user ID; a typed name cannot impersonate another reviewer.
- `backend/scripts/authoring_review_server.py`: optional loopback-only auth/review server without application lifespan, pool or scanner startup. Uses existing local accounts and the normal database module; it does not grant admin rights. Normal database initialization conventions still apply on import.
- `frontend/authoring-review.html`, `frontend/src/authoringReview/live.tsx`, `liveRecords.ts`: local adapter for the accepted F2 screen, with blind solving, answer inspection and per-dimension decisions. Existing F2 types/model/decision/source/view modules gain compatible live-data support. Main application navigation is unchanged.
- `tests/authoring_review_test.py`, `frontend/authoring-review-tests.mjs`: synthetic security and stale-evidence regressions.

## Use H2 without editing JSON

**Restart shortcut (24 October):** double-click root
`START-AUTHORING-REVIEW.cmd`, or run it by its full path from PowerShell.
It starts the loopback review API on8000 and local Vite on5948, confirms the
expected routes/page, and preserves already-running services. It does not start
scanners or mock pools. Logs stay in ignored authoring_work/review-server.
Both services had stopped after the previous session; restarting restored the
page and proxied protected API. The launcher was run twice with unchanged
listener PIDs; both direct/proxied review endpoints returned the expected401
without a session. No account credentials or reviews were changed.

**Workflow correction, 23 October:** the default page is now source comparison,
not a demand to solve questions. Compare the complete source crop against the
prepared stem/equations/four options, then choose correct / needs correction /
unsure, with an optional note. Only extraction evidence is recorded. All40 math
questions now have visually transcribed model candidates with four options.
Question15 has an additional versioned crop correction. Originals/frozen packets remain
unchanged. The older blind-solve sequence below is now an optional expert task,
inside a collapsed details section, and is not required for source comparison.

The current frontend server is on port 5948. Start the dedicated API in a PowerShell terminal if port 8000 is free:

```powershell
Set-Location C:\Users\Arsam\Desktop\Boom-merged\backend
.venv\Scripts\python.exe scripts\authoring_review_server.py
```

If the normal local backend already runs on 8000, restart it to load the new router instead of starting another server. The dedicated server avoids its pool/scanner lifespan. Do not point the frontend at the production API for this task.

1. Sign in to the local frontend with an existing local **admin** account, on the same origin/port. The page uses its existing `boom-token`; production sessions and other ports are separate. This integration does not create an admin or bypass login. If local admin credentials are unavailable, ask the project owner to provision the reviewer through the existing account administration process.
2. Open `http://127.0.0.1:5948/authoring-review.html`. Start with five math questions, including a continuation/figure example when available.
3. In **بستهٔ حل کور**, inspect the ordered original question crops and candidate text. Record a checkable independent solution before viewing the publisher's answer. Unknown symbols or incomplete context mean hold/unresolved, not a guessed repair.
4. Choose **نمایش پاسخ ناشر و داوری**. The server records answer exposure. Compare the answer with your saved solution and inspect source association. After exposure, the same account cannot submit a blind solution for this evidence version.
5. Record one dimension, decision and concrete note at a time. The typed reviewer field is only a display form requirement; the saved authoritative identity is `user:<authenticated ID>`. Scientific review requires a prior blind solution. Qualification is not certified by the system. Use a suitably qualified reviewer for scientific judgments.
6. Receipts and notes remain inspectable after reload. A changed question, source image, answer mapping, packet or catalogue causes a stale receipt or HTTP409. Reload and review the changed evidence; do not overwrite old JSON.

Stop only this optional review server with Ctrl+C. Scanner control tokens, quota state and active workers are untouched.

## Private evidence and contract extension

Inputs remain the immutable H0 S1a packet and crops under ignored `backend/data/authoring_work/s1a-mapped/`; curriculum version is the SHA of the current book catalogue. Output is ignored `backend/data/authoring_work/review-ledger-v1/<SHA(question ID)>/<random event ID>.json`. No real content is copied to tracked fixtures/docs.

SR adds an optional `evidenceToken` to the F2 binding and decision envelope, mandatory for live writes. It is a deterministic digest of the full current question, uniquely associated answer, packet digest and source/catalogue binding; it is **not** an authentication credential. Receipts bind it too, so an answer-only or pairing change cannot leave an old review marked current. Synthetic 0.1 fixtures without the extension remain compatible. Each saved receipt declares schema_version0.1; source/question revisions remain distinct from that schema version. No old formats are rewritten.

The crop bundle hash binds the ordered source-image hash list. The returned multi-part PNG is a lossless vertical presentation of those crops with white separators, not the original full PDF page. Full-page and standalone-figure hashes are null; figure presence remains unknown, not false. Page numbers are supplied; printed page/normalized options/curriculum mappings remain unknown when not recorded. No filenames or arbitrary paths are accepted by public endpoints or returned in packets.

Blind packets omit answers, publisher labels, receipts and other reviewers' solutions. Answer images are admin-only and log exposure even when accessed directly. Image requests require the current evidence token, preventing a changed image from silently accompanying an older packet. Concurrent writers use the existing OS lock on the review ledger only; a busy lock fails closed. Inputs are rechecked before decision append. An external packet mutation after append leaves a version-bound historical receipt, which becomes stale on subsequent reads; the importer does not share this ledger lock.

## Actual checks

- Backend SR + source-packet + reasoning-tag + F1 suites: **83 passed**, two existing Starlette/httpx deprecation warnings.
- Frontend review suite: **20 passed**; TypeScript exit0; normal Vite production build passed. The standalone local review entry is served by Vite development, not added to the production build/navigation.
- Read-only current-packet verification: **40 math records, 40 unique answer candidates**, zero reviews written, zero eligible records. This checks integrity/association uniqueness, not scientific correctness.
- Browser: standalone page loads on port5948 and explicitly requires local admin login. No real authenticated human decision was simulated or forged. The integrated authenticated flow is covered with synthetic TestClient fixtures; real H2 session interaction remains a human handoff.
- Tests include missing/nonadmin authorization, spoofed reviewer, model attribution rejection, stale content/answer/image/catalogue/packet, malformed source and ledger, unknown paths, ambiguous answer associations, blind-solve exposure ordering and append-only conflicting decisions.

## Remaining limits and next handoff

H2 must supply actual attributed reviews. Source crops/candidate extraction do not yet provide normalized ordered-option correction or curriculum-node editing in this interface; discrepancies should be held with precise notes and passed to a versioned source-correction task. No scientific authority, clean holdout, source eligibility or release readiness is inferred. Supersession/adjudication and conversion of these receipts into retrieval eligibility are separate reviewed integration tasks.

Next: H2 reviews the small math sample using this interface; Sol checks the resulting version-bound records and resolves source defects before later authoring stages. Final split qualification remains separate. No new source upload is required to begin this review.

## Startup correction — 23 October

User reproduction found no API listening on8000 and an empty review selector. Started the dedicated loopback review server and added inline normal local-admin login, reconnect, persistent failure messages and disabled empty controls. Three local admin accounts exist; credentials were not read or changed. Browser verified the visible login-required state; live unauthenticated endpoints return401.20 frontend tests passed, including the live-entry login/reconnect regression; TypeScript exit0. No human reviews were fabricated.

## Source comparison repair — 23 October

Added SourceCheck.tsx and a versioned private presentation adapter in the review
store. Private candidates are hash-named files under review-candidates-v1, bound
to their parent content/image hashes and original PDF SHA. Only a fixed local
pointer chooses the candidate; clients cannot supply paths. Transcribed math
renders with KaTeX; the original packet/native extraction is never rewritten.
Corrected source crop includes the previously clipped superscripts/fraction.
Only question1 was visually transcribed; no bulk OCR or review occurred.

Every decision binds the displayed candidate and crop. Candidate changes
invalidate earlier bindings; bare native candidates cannot receive extraction
passes. Blind mode exposes only the same account's extraction checks, not
scientific receipts or other people's solutions. Answer exposure now blocks
later blind solving across presentation-only revisions too. No scientific
review, eligibility or retrieval approval is inferred.

Latest checks:85 related backend tests passed;16 SR tests passed again after
final hardening;23 frontend tests and TypeScript passed. Browser verified real
question1 renders its powers, fraction and four options with the answer hidden.
No review buttons were pressed by the agent. Current API is the dedicated local
review server; no production changes or provider calls. Full-source comparison,
optional zoom and the three decisions replace misleading synthetic/developer
messages; advanced expert evidence remains available separately.

Question2 follow-up (23 October): added a visually transcribed private candidate revision2 and a complete source crop.2/40 math questions now have structured candidate presentations;38 remain pending. Browser verified question2's two functions, composition notation and four options. No review decision or answer exposure was performed by the agent.

## Complete 40-question preparation — 23 October

Supersedes the earlier two-question preparation count. All40 math items now have
structured candidate stems and four ordered options (160 total). The original
six question pages were inspected visually; formulas were transcribed with
explicit LaTeX.209 math expressions passed KaTeX syntax validation. All40 items
were loaded in the authenticated browser with four options and no math-render
errors. This is rendering/source-preparation evidence, not scientific approval.

`backend/scripts/prepare_review_presentations.py` builds immutable hash-named
private candidates from locally prepared transcriptions and verifies the source
PDF SHA before opening it. It resumes by preserving existing candidates; the
synthetic test checks repeat runs and SHA mismatch. Questions1/2 and their review
history were preserved. Question15's clipped piecewise definition received an
additional candidate/crop revision; superseded artifacts remain intact.

Candidate page projection now uses the actual displayed crop page. Original
page-end spillovers remain in the parent packet but no longer add irrelevant
covers/physics to the review image (notably question40). Existing source figures
and the statistics table remain visible; related candidates explicitly mention
the source figure/table. Math options render through the existing safe math
renderer. No labels, solutions, answer claims or human approvals were invented.

Private evidence: review-candidates-v1/remaining-math-draft.json,
preparation-status.json and preparation-validation.json. Original PDF, frozen
packet, answer associations, vectors and quota state are untouched. Temporary
inspection renders were removed after validation; current and superseded source
crops remain. No VM work, push, provider call or new human decision was made.

## Shared math typography correction — 24 October 2026

- Fixed the review option-label selector so it no longer overrides every nested KaTeX span. Added vertical padding around horizontally scrollable math and explicit direction for numeric options.
- Aligned the direct KaTeX dependency/stylesheet with rehype-katex's renderer at 0.16.47. The former 0.18.9 stylesheet expected renamed internal classes and broke sizing and limit placement. A regression test now checks matching versions.
- Review presentation displays floor as square brackets; explicit composition remains `\circ`. Canonical transcription, source hashes and existing human receipts are unchanged. No ambiguous prose replacement of `fog` is performed.
- Actual checks: 26 frontend review tests passed; TypeScript passed; production frontend build passed. Authenticated browser checks on questions 2, 15, 17, 27 and 39 found four options, no KaTeX errors and no vertical scroll-container clipping. Question 14's limits/fractions were visually checked after restarting the owned Vite server to refresh cached CSS.
- These checks establish presentation behavior, not scientific correctness or complete transcription fidelity. Reviewers should report recurring display defects once; missing/wrong source terms or signs remain per-record extraction defects. Existing failure receipts remain available for human reconsideration; no agent approvals were written.

## Human report correction pass — 24 October 2026

The saved ledger contains 48 extraction events covering all 40 pilot questions;
latest first-pass outcomes were 27 passed, 12 failed, 1 unresolved. All were bound
to current evidence before this correction pass. No scientific review is inferred.

Versioned private corrections changed questions 2,7,9,14,16,20,21,26,36,40.
They match the printed composition `o`, fix a missing digit, restore triangle
markers, match printed set subtraction, remove neighboring-question crop fragments,
and replace the prose data list in question40 with a two-row numeric table.
Prior candidate files, source PDFs, frozen packet and human ledger remain intact.
Shared renderer corrections also require visual reconsideration of 5,11,15,30;
question11 had a pass with an overlap warning, so it is included explicitly.
Unchanged approvals are preserved; new revisions require a fresh human comparison.
The simple UI now shows the older report when current evidence has changed.

Checks: all40 candidate/source/answer image hashes validate; all40 have exactly
one answer association by exam/session/booklet/section/printed number. All40
answer crop edges were inspected in private contact sheets. Some original answer
images include neighboring question fragments or header-only continuation regions;
this pass did not rewrite original answer crops or assert full solution/OCR
fidelity. This is a recorded limitation, not new human approval.

Authenticated browser checks on all14 affected items found four options each,
zero KaTeX errors and zero vertical scroll-container clipping.17 backend review
tests and27 frontend review tests passed; TypeScript passed. No agent decisions,
answer exposure through the user's account, provider calls, deployments or pushes.

Private evidence: `backend/data/authoring_work/review-candidates-v1/correction-status-2026-10-24.json`
and `correction-inspection/answer-edges-*.png`. Next handoff: user rechecks only
2,5,7,9,11,14,15,16,20,21,26,30,36,40 on the local review page. Remaining H2
answer/curriculum/design judgments are separate from this text-comparison pass.

### Question40 follow-up — labeled source table

User confirmed the other corrections and reported missing row labels in question40.
Added an optional validated source table to candidate presentations; both row labels
and all ordered cells are bound into the content hash. Absent tables preserve the
existing binding format. Unequal/malformed rows fail closed. The simple review UI
renders an escaped semantic HTML table with RTL row labels and LTR numeric cells.
Question40 received a new immutable candidate restoring حدود دسته and فراوانی;
previous candidates/reports remain intact. No human decisions were written.
18 backend review tests,28 frontend review tests and TypeScript passed. Browser
visually confirmed labels, interval/frequency order and four options against the
source crop. Only question40 needs the user's new comparison. No deployment.
