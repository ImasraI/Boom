# F2 integration review — 23 October 2026

Status: changes required, not accepted. Reviewed isolated frontend/src/authoringReview and frontend/authoring-review-tests.mjs. No Freebuff-owned files changed by this audit.

Actual checks: node --test authoring-review-tests.mjs:12 passed. node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json:exit0. The initial npx command was blocked by local PowerShell signing policy; direct TypeScript execution succeeded without changing policy. No browser visual/interactive acceptance yet because evidence-state blockers were found first.

Reproducible synthetic probes through Vite SSR:
1. Put a current human passed receipt and a current failed receipt for the same dimension on q1, with disagreements empty. evidenceStateFor returns verified_human. Neither an explicit failure nor unresolved conflicting judgments may silently disappear behind a pass. Preserve receipt history; resolve using explicit adjudication/supersession, or show disagreement/held. Add tests for pass/fail, failure after pass, and superseded failures.
2. Change q1 questionId to another ID while keeping its hash/revision. isReceiptCurrent still returns true for q1 receipt. EvidenceReceipt lacks questionId binding. Add exact question ID, source document/revision, source/figure image hashes, and applicable catalogue version binding. Content hash alone does not prove source images/catalogue unchanged. Reject stale/missing bindings rather than assuming current.
3. Decision payload currently carries questionId/revision/contentHash only. Carry the exact image/source/catalogue evidence the reviewer saw (or an opaque server-issued evidence revision token); require the eventual server to reauthorize identity and recheck those bindings atomically. ReviewerIdentifier input is attribution only, never authenticated reviewer authority. No live endpoint wiring in F2.

Copyable Freebuff correction prompt:

```text
Read docs/production-work-pack/F2_REVIEW.md, CONTRACTS.md and REASONING_TAG_CONTRACT.md. Correct only your assigned frontend/src/authoringReview/* and frontend/authoring-review-tests.mjs, and update your handoff. Fix conflicting/stale receipt display and complete question/source/image/catalogue binding without inventing human approvals or a server. Keep no-API mode read-only and synthetic fixtures unmistakably synthetic. Add adversarial tests that would fail on the two reproduced bugs. Preserve other agents' work. Run the focused tests and TypeScript directly if PowerShell blocks npx. Return exact outputs and remaining integration dependencies; do not wire application routes or claim F2 accepted. Sol will then review and test actual browser interactions/layout before marking complete.
```

Useful existing properties: approved static source IDs restrict image destinations; React text escaping is tested; absent decision API is read-only; evidence dimensions and synthetic examples are explicit. These do not compensate for incorrect receipt-state logic.

## Acceptance recheck — 23 October 2026

F2 accepted as isolated synthetic review UI. Fresh results:17 focused tests passed; TypeScript exit0. New tests reproduce and fix earlier contradictory human receipts, question/document/image/catalogue binding and decision payload gaps. Browser checks on standalone port5948 passed: RTL rendering,125% zoom, receipt expansion, ArrowDown record change, missing-image/continuation states, light/dark,390px phone layout (no horizontal overflow:scrollWidth=clientWidth380), and q=syn-0005-q5 deep link. Temporary viewport reset; test tab closed. Snapshot saved outside project in Temp/boom-f2-checked.png.

Remaining SR integration: authenticated decision API, atomic server evidence binding including answer-key/pairing version, real private source adapter and authorized images. F2 completion does not assert any deployed functionality or real human reviews. Earlier changes-required status is superseded for this scoped UI acceptance.
