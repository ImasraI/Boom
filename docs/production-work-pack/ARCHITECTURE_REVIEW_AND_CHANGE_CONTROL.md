# Architecture findings and revision checkpoints

Local audit of the current working tree. This is not a deployed-state audit,
permission to migrate Chroma or approval to delete user data.

## Confirmed findings

| Area | Evidence | Decision |
| --- | --- | --- |
| Legacy document API | `backend/app/main.py` still registers `documents.router`; POST `/api/documents/upload`, GET and DELETE remain authenticated routes | Hidden UI does not disable an API. Decide public feature scope before deprecating the routes; do not call them dead code. |
| Two PDF ingestion paths | `documents.py` branches on `PDF_PROCESSING_MODE`: text extraction/chunking versus PDF-page image embeddings | These are two processing modes, not two currently found frontend attachment controls. The API accepts PDF/TXT/MD, not standalone PNG/JPEG. |
| Current chat attachment controls | No PDF/image file input or document-upload call found in the searched current frontend source | Report search scope, not a guarantee about every deployed asset or historical commit. |
| Fake result upload | `frontend/src/pages/Exams.tsx` had a timer-only upload card, reachable through the compiled Exams screen | Removed the fake control, handler and temporary success states. Kept real result retrieval/display. No real import workflow was removed. |
| Shared image ingestion | `backend/app/rag/ingest_raw.py` calls `ingest_pdf_as_images` | Keep page-image processing; removing legacy upload UI does not make book diagrams or image retrieval obsolete. |
| Legacy vector ownership | `vector_store.py` and `hybrid_search.py` include the requester and configured `DEMO_USER_ID` in retrieval | User ID is ownership/access metadata, not a separate embedding per student. Preserve filters until a tested replacement exists. |
| Shared corpus owner overload | Default `DEMO_USER_ID=1` is reused as the shared corpus namespace | If private content is written under this owner, retrieval can expose it as shared. This is a design risk; no actual private-record leak was established in this read-only audit. |

The vector-store module's old single-user-only description was corrected to match
the actual shared-plus-private search behavior. Metadata currently serves multiple
purposes; `user_id` does not replace source identity, source role, curriculum,
review eligibility or evaluation-split filtering.

## Target separation; not an implemented migration

- Shared corpus: stable document/source/content IDs, classification, curriculum,
  evidence/review and split metadata. Store a book once for all students.
- Private optional corpus: explicit owner and access scope, authenticated writes,
  scoped retrieval and deletion. Do not put private material under a shared owner.
- Student profile, progress, homework and answers: application database with
  account ownership. Do not embed every scalar profile field just because Chroma
  exists. Embed private narrative memory only for an identified retrieval need.

Prefer explicit `visibility`/`corpus_id`/nullable `owner_user_id`, or a separately
managed shared/private collection boundary. Preserve existing vectors and their
embedding-model identity. A namespace migration needs an inventory, explicit
shared/private classification, backup, dry run, row-count/hash reconciliation,
cross-account tests, deletion tests and rollback. No dropping `user_id`, wholesale
re-embedding or live migration is authorized by this audit.

A public-upload deprecation task must trace callers, scripts, storage cleanup,
OpenAPI/client contracts, existing private uploads and source eligibility. If
retained, private uploads must remain untrusted user evidence and must not become
approved textbooks or exam designs through fallback retrieval. A hidden control
is not an access-control decision. Admin corpus imports remain separate.

## Adaptive roadmap rules

Phases track dependencies and evidence; they are not a fixed script to follow
after contrary evidence appears. At each source, authoring, integration and
release checkpoint, record:

1. Finding and concrete evidence (code path, test, bound receipt or user feedback).
2. What was previously assumed, what changed and what remains uncertain.
3. Impact on source identity, privacy, correctness, eligibility and downstream tasks.
4. Decision: fix now, bounded experiment, defer with reason, or remove after caller audit.
5. Owner, writable files, prerequisites, actual checks and next handoff.

Keep completed work and frozen experiments historical. Reopen affected gates
explicitly when their assumptions become false. Do not turn changed requirements
into retroactive failure/success metrics. Update TASK_BOARD/README with the current
handoff rather than adding unrelated work to the active task silently.

Current additions: error-derived distractors and validated shortcuts; readable
parameter choices and schematic fidelity; public/private corpus boundary review;
legacy upload lifecycle review. Current removal: fake result-upload UI. Current
hold: broad vector ownership migration and backend upload removal until caller,
data and policy requirements are resolved.

## Independent architecture review

A separate GPT Astra review can help challenge assumptions and find omissions.
Give it bounded source/diff evidence and acceptance criteria. A reviewer cannot
certify correctness by agreeing with the implementation or infer what was deployed
from local code. Mathematical expert review and student evidence remain distinct.
The integrator reviews findings and implements/tests accepted changes; two agents
must not edit the same files without declared ownership.

Copyable review prompt:

```text
Review the Karzar/Boom production plan and current implementation read-only.
Read AGENTS.md, docs/production-work-pack/README.md, TASK_BOARD.md,
CONTRACTS.md, ARCHITECTURE_REVIEW_AND_CHANGE_CONTROL.md and
AUTHORING_DISTRACTORS_AND_SHORTCUTS.md. Inspect only the source/diff needed.
Do not read .env, worker credentials, private corpus files, student records,
sealed holdouts or ignored data. Use synthetic examples. Do not run paid calls,
scans, migrations, workers, deployment or provider probes. Do not edit files.

Challenge these areas: shared/private retrieval isolation; source-role and split
filters before ranking; hidden but active upload endpoints; question correctness
versus teaching quality; distractor traces; valid shortcuts versus answer leakage;
diagram legibility versus mathematical fidelity; stale review invalidation.

Return concrete findings ordered by severity, with owning code/document location,
an observable failure scenario, evidence, uncertainty and a minimal proposed fix.
Separate observed defects from risks and hypotheses. Identify obsolete tasks,
missing dependencies and gates that must reopen. Do not infer human review,
empirical difficulty, originality, deployment state or science from model agreement.
Finish with a small prioritized task list, ownership and meaningful acceptance tests.
No broad rewrite recommendations without evidence of the problem they address.
```
