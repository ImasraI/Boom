# User feedback: account access, identity and saved test review

Scope: local fixes following a tester's report relayed by the project owner.
No provider calls, SMS delivery tests, deployment, VM access or private data edits.
Other work and authoring experiment checkpoints remain untouched.

## Confirmed gaps and changes

- Password reset already existed in the signup/account-exists flow. Login lacked
  an entry. Login now links to a three-step phone/code/new-password flow, reusing
  the backend OTP verification and explicit reset flag. No verification bypass
  was added. New-account onboarding remains separate.
- Arena returned `User.username`, commonly a phone identifier. Leaderboard joins
  the saved profile and uses its name; opponent/host displays use the same rule.
  Phone-like names/usernames fall back to a generic player label. Existing API
  field `username` remains compatible. No account usernames are rewritten.
- Mock attempts were persisted, but the frontend had no reopening UI. The mock
  entry now lists completed tests with dates, titles, scores and answer-review
  links, paginates older attempts, and offers retry on history fetch errors.
  `GET /api/mocks/attempts/{attempt_id}` requires the attempt owner's identity.
  Reading uses the saved result snapshot and does not submit/rescore or create
  new weakness entries. Legacy incomplete results are explicitly marked.

## Suggested feature order (not implemented by this patch)

1. Pick multiple topics from the current book-backed catalogue; assign question
   counts per topic. Validate totals, major/grade and actual verified bank stock.
   Report unavailable quotas rather than silently substituting other topics.
2. An answer-sheet "explain this question" action carrying question ID/revision,
   the student's choice, diagram and solution context to the tutor. Treat model
   explanations as fallible and preserve cited source/provenance.
3. Surface the existing study-session backend in a simple planned-versus-actual
   UI. Duration is self-reported unless a timer was actually used; do not turn
   time spent into a mastery score.
4. Class notes/PDF-to-practice as a private draft workflow with extraction preview
   and verification. Source uploads must not enter the shared question bank
   automatically. Voice transcription adds Persian/math transcription errors,
   recording-consent questions, storage and free-quota costs; pilot after PDFs.
5. A discussion board is feasible but needs moderation, reports, privacy and
   participation. Begin with a small Q&A pilot after the core test loop works.

These are implementation priorities based on this repository, not a reviewed
comparison with the mentioned third-party sites/bot.

## Checks

- 84 backend tests passed across historical attempts, arena display names,
  auth/reset protection, arena compatibility and mock API regressions.
- Three new frontend render tests cover login recovery visibility, recovery
  starting at the phone step, and saved-review history discovery.
- Final full frontend suite: 105 passed. One new test initially expected an
  unformatted phone string and was corrected to the actual formatted input.
- TypeScript and production build passed. Tests use synthetic users and
  isolated SQLite. Existing Vite test workers printed HMR port-in-use warnings;
  all tests completed and their servers closed normally.

Limits: no live SMS sent, no deployed frontend/backend updated, no end-to-end
browser login/SMS delivery assertion. Existing provider/production configuration
still determines OTP availability. Historical results whose original scored
subset cannot be recovered retain totals and withhold invented per-question data.
