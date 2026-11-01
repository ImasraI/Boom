# Current question storage — 29 October 2026

Code reference: `backend/app/auth/database.py` and `backend/app/rag/question_bank.py`.
This describes the current ORM/application contract, not a schema redesign.
Experimental authoring files are separate from the production SQL bank.

## `bank_questions`: one reusable question

All fields below are non-null except `created_at`. Primary keys are implicitly
non-null. Defaults are ORM defaults, not necessarily SQLite server defaults.

| Column | SQLAlchemy type | Properties / meaning |
| --- | --- | --- |
| id | Integer | Primary key; internal stable bank identity |
| fingerprint | String | Unique, indexed, required; SHA-256 deduplication key |
| owner_id | Integer | Indexed; default 0 means shared; other values select the student's private bank. Not declared as a foreign key |
| major | String | Indexed; default empty string |
| grade | String | Default empty string; grade display value |
| grade_level | Integer | Indexed; default 12; normalized grade |
| difficulty | String | Indexed; default `konkur`; legacy selection label, not measured difficulty |
| subject | String | Indexed, required; broad subject such as mathematics |
| topic | String | Default empty string; free-text topic, not a confirmed catalogue-node ID |
| content | Text | Required JSON text containing the question payload; not a normalized SQL object |
| verified | Boolean | Default false; application verification flag, not proof of human review |
| status | String | Indexed; default `active`; `corrupt` and `deleted` are excluded from future selection |
| uses | Integer | Default 0; usage counter |
| admin_note | Text | Default empty string |
| created_at | DateTime | Nullable; ORM UTC timestamp default |

Fingerprint inputs are owner, category (`mock` or `assessment`), subject, stem,
options and answer. Topic, figure, explanation and presentation IDs are not in
that fingerprint; therefore it is not a complete content-revision hash or a
semantic-originality detector.

The JSON keeps question fields other than presentation `id`/`_id` and `bank_id`.
Typical fields: `subject`, `topic`, `text`, four `options`, zero-based integer
`answer`, `explanation`, `figure`, `verification_status`, plus optional book/page,
source/grounding and curriculum metadata supplied by a particular generator.
These optional properties are not all guaranteed to exist or be reviewed.

The bank's basic shape check requires nonempty text, exactly four nonempty string
options and an integer answer 0–3. It does not establish mathematical validity.
Selection additionally filters ownership, major, grade, difficulty, active status
and the verification flag. There is no normalized reasoning-tag column here.

## Related production tables

| Table | Columns | Purpose |
| --- | --- | --- |
| generated_mocks | id, student_id, title, major, grade, duration_minutes, questions, status, difficulty, bank_scope, bank_indexed, created_at | A booklet and its JSON question snapshots; student_id references users |
| mock_attempts | id, mock_id, student_id, answers, duration_seconds, score, correct, wrong, blank, result_snapshot, created_at | Student answers and historical scores; JSON result_snapshot freezes the scored review; mock_id/student_id are foreign keys |
| question_reports | id, question_id, student_id, mock_id, reason, created_at | Reports; question_id/student_id/mock_id are foreign keys; unique(question_id, student_id, mock_id) |
| pool_draft_jobs | id, config, major, difficulty, grade, plan, questions, status, question_count, verified_count, rejected_count, lease_owner, lease_until, retry_at, created_at | Durable drafting/verification queue; not the released question bank |

`answers` is a question-ID-to-answer JSON object. `result_snapshot` contains a
schema version, mock/student identities and the saved response. Reading a finished
attempt must not regrade it against today's quarantined/restored bank contents.

## Local benchmark: candidate JSON, not SQL rows

Each of the 24 experimental drafts has:

| Property | Type / meaning |
| --- | --- |
| text | Persian question stem with math delimiters |
| options | Four strings |
| answer_index | Integer 0–3 |
| solution | Author-model's short derivation; distinct from independent checks |
| design.givens | Stated givens |
| design.unknown | Requested quantity/property |
| design.domains | Domains and feasibility conditions |
| design.essential_insight | Model's proposed central insight |
| design.structural_departure | Model's claim of design difference; not originality approval |
| design.tempting_wrong_route | Model's proposed misleading approach |
| figure | Null or typed points/segments, rendered by trusted code |

The execution/review sidecars additionally bind prompt, response, candidate and
presentation hashes; model/settings; experiment arm; task identity; failures;
checks; and correction deltas. The R alias is a review identifier, not a SQL ID.
Raw drafts, assistant proofs and repaired displays remain separate revisions.

## Reasoning annotations: separate versioned contract

`backend/app/rag/reasoning_tags.py` validates the draft taxonomy contract.
Top-level properties are `annotation_schema_version`, `taxonomy_version`,
`annotation_revision`, `question_ref`, `question_revision`, `source`,
`catalogue_version`, `knowledge_ids`, `knowledge_evidence`, `objective`,
`representations`, `routes`, `checks_shortcuts`, `misconceptions`,
`unresolved_labels`, `annotator`, `review`, `intended_difficulty`,
`empirical_difficulty`.

Routes distinguish primary and alternative solutions; technique roles distinguish
primary, supporting and checking. Knowledge IDs need versioned book-backed
catalogue evidence. Technique presence does not establish difficulty, an author's
private thought process, or student weakness. These annotations have not yet been
assigned to the 24 benchmark drafts.

## Identified solution-writing gap

The frozen benchmark asked for a **short checkable derivation**, not a polished
student solution explicitly aligned with its reasoning tags. Independent finite
enumeration can verify a result but should not become the only student-facing
explanation. Future experiments should separately record a checked pedagogical
solution, an optional alternate route and a technique-to-visible-step mapping.
Do not change the frozen experiment prompts or retroactively claim they had
those requirements. Existing drafts need separate versioned explanation edits.
