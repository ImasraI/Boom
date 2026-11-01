# F2 handoff — review interface, correction round — 23 October 2026

Status: both defects recorded in F2_REVIEW.md are corrected with adversarial
tests. F2 stays **unchecked**: Sol must re-run the probes and do the planned
browser interaction/layout acceptance before marking it complete. Isolated
frontend only — no routers, packages, shared schemas, servers, credentials or
other agents' files were touched, and no deployment was performed.

## Files changed in this round

- `frontend/src/authoringReview/types.ts` — new `EvidenceBinding`
  (question id/revision, content hash, document id/revision, page/crop/figure
  image hashes, catalogue version); receipts now carry `binding` + `supersedes`
  instead of bare revision/hash; `EvidenceState` gains `rejected`; `ReviewSource`
  gains `documentRevision`/`pageImageHash`/`cropImageHash`; `FigureInfo` gains
  `imageHash`.
- `frontend/src/authoringReview/model.ts` — `bindingFor`,
  `receiptBindingGaps`, `BINDING_FIELD_LABELS`; `isReceiptCurrent` now means
  "zero binding gaps" (missing, empty or changed fields all reject);
  `evidenceStateFor` rewritten with conflict rules and same-kind supersession;
  labels/describes for `rejected`, stale and unresolved states.
- `frontend/src/authoringReview/decisions.ts` — `ReviewDecisionInput` carries the
  full `binding`; `buildDecisionInput`/`submitDecision` refuse records whose own
  binding is incomplete, so an unbound decision can never reach the API.
- `frontend/src/authoringReview/fixtures.synthetic.ts` — every record and receipt
  carries the S0-shaped binding (image hashes are null only where the approved
  set genuinely has no image); replaced the banned `□` (U+25A1) glyph with `?`
  to satisfy the emoji-free rule.
- `frontend/src/authoringReview/AuthoringReviewView.tsx` — `rejected` tone/label;
  stale receipts list the exact mismatched fields; `جایگزین‌شده` badge plus note
  for superseded receipts; receipt meta shows document/revision/catalogue;
  decision note and no-API dependency text document the `evidence_binding`
  contract and the atomic 409 recheck.
- `frontend/src/authoringReview/dev-preview.html` — optional `?q=<question_id>`
  deep link for QA (default behaviour unchanged).
- `frontend/authoring-review-tests.mjs` — 5 new adversarial tests (17 total).
- `docs/evidence/f2-review-*.png` — refreshed (8 shots, including new
  `f2-review-stale-bindings.png`).
- `frontend/.freebuff-capture.mjs` — screenshot helper (untracked; `CAPTURE_BASE`
  overrides the dev-server URL).

## Defect fixes (as reproduced in F2_REVIEW.md)

1. **Conflicting pass/fail receipts displayed "human verified."**
   `evidenceStateFor` now resolves, in order: explicit record disagreement →
   current conflicting human pass+fail = `disagreement` (a failure, including
   one recorded after a pass, never disappears behind a pass) → lone current
   human failure = new `rejected` state ("رد انسانی") → human unresolved blocks
   → only then `verified_human`. Model pass+fail is likewise `disagreement`;
   model failure alone can never read as model verification. Only receipts that
   are binding-current *and* not superseded participate; supersession applies
   only within the same reviewer kind, so a model receipt can never erase a
   human judgment. Superseded/stale receipts stay on screen with badges —
   history is preserved, never silently deleted.
2. **Receipt validity did not bind question id / source-image / catalogue
   evidence.** Every receipt now carries an `EvidenceBinding`; `bindingFor`
   derives the record's exact evidence set and returns `null` for incomplete
   records (e.g. an image without a hash); `receiptBindingGaps` reports each
   missing/changed field and `isReceiptCurrent` is `gaps.length === 0`.
   Missing bindings are rejected, never assumed current. Probe 2 (record
   questionId changed while revision/hash kept) now yields `false`/`stale`.
3. **Decision payload too thin.** `ReviewDecisionInput.binding` carries the
   exact document/image/catalogue evidence the reviewer saw; the documented
   contract tells the server to reauthorize identity from the session and
   recheck every binding atomically (409 on mismatch). `reviewerIdentifier`
   remains attribution only. No endpoint was implemented or wired.

## Actual checks (exact outputs)

- `node --test authoring-review-tests.mjs` → `# tests 17 / # pass 17 / # fail 0`
  (12 previous tests still pass; new: conflicting/failing receipts never become
  human verification; superseded/stale failures cannot block a current pass;
  receipts bind question id/document/image hashes/catalogue; stale receipt names
  the exact mismatched bindings; decision payload carries the full binding and
  refuses incomplete records).
- `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json` → `tsc exit: 0`
  (direct invocation; local PowerShell signing policy still blocks `npx`).
- `node --test emoji-free-tests.mjs` → `pass 4 / fail 0` (this surfaced the
  pre-existing `□` in the F2 fixture; fixed in F2-owned files).
- `npm test` → `# tests 102 / # pass 102 / # fail 0` (whole frontend suite).
- `npm run build` → `✓ built in 1.66s`.
- Independent replay of the three F2_REVIEW probes via Vite SSR printed:
  `probe1 state = disagreement`, `probe2 isReceiptCurrent = false`,
  `probe3 binding keys = catalogueVersion,contentHash,cropImageHash,documentId,
  documentRevision,figureImageHash,pageImageHash,questionId,questionRevision`,
  `ALL THREE PROBES NOW HOLD` (temporary probe script removed afterwards).

## Evidence (synthetic data only)

`docs/evidence/`: `f2-review-desktop.png`, `f2-review-evidence.png`,
`f2-review-decision.png`, `f2-review-dark.png`, `f2-review-mobile.png`,
`f2-review-mobile-options.png`, `f2-review-mobile-decision.png`, and new
`f2-review-stale-bindings.png` (q4 via `?q=syn-0004-q4`, receipts expanded:
stale receipt shows `منقضی` plus the exact gap fields — نسخهٔ پرسش، هش محتوا،
هش تصویر برش — and the current receipt shows its document/catalogue binding
metadata).

## Remaining limitations / integration dependencies

- **No decision API exists**: the screen stays read-only and names the
  dependency. SR must implement `POST /api/authoring/reviews/{question_id}/decisions`
  with session-derived identity, atomic recheck of every binding field (409 on
  mismatch), append-only receipts with `supersedes`, and server-side eligibility.
- The screen *displays* supersedes but cannot establish who may supersede what;
  that authority stays server-side.
- Receipts are trusted as server-shaped objects: `schema_version`, `evidence_refs`
  and per-receipt issue lists from the S0 contract are not modeled in F2.
- Answer-key image hashes and pairing revision are not in the F2 binding (the S0
  receipt lists source/figure hashes + curriculum); SR should bind them
  server-side if the decision write needs them.
- A record whose own binding is incomplete renders as `stale` (safe direction:
  nothing approves); a dedicated "record incomplete" display would need a
  contract state.
- The `rejected` and pass/fail-conflict states are exercised by tests, not by
  the default fixtures; inspect them through the test renderers or ask for a
  fixture extension.
- Dev server for QA runs at `http://127.0.0.1:5948/` (vite no longer pins 8443 in
  this checkout); `frontend/.freebuff-vite.log` holds its log.

## Next handoff

Sol: re-run the F2_REVIEW probes against `frontend/src/authoringReview/*` (the
new tests reproduce all three), then do the browser interaction/layout QA —
RTL, keyboard roving, zoom, narrow screens, `?q=` deep links, dark/light,
receipt expansion — before deciding on F2. Monitor/router wiring and
authorization enforcement remain Sol's (SR) scope.
