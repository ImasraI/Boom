# Mock and ranked diagnosis — October 6, 2026

The public frontend and API are online. Authenticated ranked identity, subject filters and leaderboard reads passed for the existing accounts. The current Mock, Arena, shared math and question-report JavaScript files return JavaScript with HTTP 200. Both page modules also pass rendering tests with empty account preferences.

The reported «صفحه آماده نشد» is the frontend error boundary. A stale or interrupted download of a lazy page is a plausible cause, but the precise exception in the affected browser has not been captured. The available browser session reached login; the documented test-account password was rejected, so an authenticated visual reproduction was unavailable. The application now distinguishes page-download failures from rendering failures, reloads once for a failed page download, and restores the selected panel. Offline failures and ordinary rendering exceptions do not cause reload loops.

Practice generation was tested with a temporary copy of the production database and with a real authenticated public request. The legacy saved booklets have no verified answer-key markers, and the verified question bank is empty. All copied-account practice scenarios required live generation. The public request correctly returned HTTP 503 with `provider_daily_quota`; no exam was created and the provider was not probed. The recorded retry time is October 7, 2026 at 07:00 UTC, or 10:30 Tehran. This is a retry time, not a guarantee of available provider capacity.

Changes:

- Panel requests have timeouts and visible retry/error states. Mock generation can be left without clearing the account. Ranked exam time starts after questions arrive.
- A blocked provider and empty shared stock refuse ranked joining before queueing or charging usage. Failed/incomplete generation cancels the match without scores or rating changes, preserves verified survivors, and reports the failure. Old empty matches expire instead of waiting indefinitely.
- Mock generation uses the saved account's major and grade ahead of a stale browser cache. Practice continues to prefer previously used verified questions, with fresh verified stock as fallback when none has been used.
- Admin stock counts and worker deficits count verified usable booklets; legacy and reported booklets remain stored for review and are not labelled ready.
- An optional ignored quota-state file stores only credential/model fingerprints and reset timestamps. Enabling it on the VM preserves terminal provider limits across deployments without exposing keys or repeatedly probing exhausted quota.

Validation: 455 backend tests passed with 3 skipped; 30 frontend tests passed; TypeScript and the Cloudflare production build passed. Successful generation, taking/scoring, ownership, reporting, private/shared question separation, and ranked fallback are covered with isolated verified stock. Production generation remains unavailable until the provider can verify or generate eligible questions; old questions were not relabelled as verified to make a test pass.

Deployment preserves the application database, account history, uploads, JWT secret and shared vectors, with SQLite backup through its backup API and a Chroma backup while writers are stopped. No login SMS was sent.
