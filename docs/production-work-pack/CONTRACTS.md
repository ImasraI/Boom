# S0 contracts — v0.1 draft

SR additive extension (23 October): live F2 bindings/decisions carry an
`evidenceToken` for the question, answer association, source packet and catalogue.
Receipts bind it; missing/changed live tokens are stale. Existing synthetic 0.1
records remain compatible. See [SR_HANDOFF.md](SR_HANDOFF.md) for API/storage
semantics and limits. This extension does not change source revisions or grant
eligibility.

22 October 2026. Contract agreed for development by the S0 integrator; source identity, curriculum and expert decisions remain pending. This document defines interfaces only; no adapter, migration or approval is implemented by S0.

## Compatibility and identity

Preserve `exam_candidate_index.py` schema 1 parents (`id`, `literal`, `content_sha256`, `metadata`) and frozen snapshots. Preserve the flatter `exam_style.py` records and existing question-bank IDs. Add sidecar records keyed to those IDs. The fuller `QUESTION_DESIGN_SCHEMA.md` is a proposal, not today's stored format. Reasoning annotations follow candidate taxonomy 0.1.

Schema version means field/validation semantics. Document revision means changed PDF bytes (new SHA and document ID). Question revision means changed literal/options/figure content. Annotation revision means changed interpretation without changing the question. Never use one counter for all four.

Document ID = SHA256 of original PDF bytes. Existing question IDs remain document SHA:one-based PDF page:printed question number; never renumber them. New multi-page questions receive an immutable opaque ID and explicit legacy aliases, never a silently reassigned old ID. Exam identity and pairing are separate from filenames and question IDs. Duplicate bytes have aliases, not new content identities.

## Minimum records

Unknown scalar values are null. Empty arrays mean no recorded entries, not completed review. References are local relative paths beneath the approved private root; reject traversal, absolute outside paths and embedded instructions. Hashes are lowercase 64-character SHA256. Do not fabricate hashes in real records.

| Record | Required fields and semantics |
| --- | --- |
| Document | schema_version, document_id/source_sha256, role (`questions`, `answers`, `combined`, `unknown`), classification (`official_exam`, `mock_exam`, `textbook`, `mock_plan`, `unknown`), classification_state (`inferred`, `confirmed`, `unresolved`), publisher/year/session/major/grade/booklet_code, exam_id, revision, aliases, classification_evidence |
| Pairing | pairing_id, revision, question_document_id, answer_document_id, exam_id, session, booklet_code, mapping entries, state and reviewer/evidence. Match printed question number plus section/booklet; never assume equal PDF page offsets. Combined documents may reference themselves. Ambiguous/multiple keys remain unresolved. |
| Question source sidecar | question_id, question_revision, document_id, printed_question_number, section, regions[], literal_content_sha256, source_image_sha256[], figure_sha256[], answer_provenance, issues. Regions carry one-based pdf_page, nullable printed_page, normalized bbox [left,top,right,bottom] in original-page orientation and render metadata. Continuations retain all parts and their hashes. |
| Answer provenance | answer_document_id, regions[], printed_question_number, section/booklet, raw_key, normalized_answer_index (0..3 in printed order), mapping_state, pairing_revision. An author's key is distinct from a verified scientific answer. |
| Review receipt | receipt_id, schema_version, question_id/revision, content hash, exact image/figure hashes, curriculum_version, reviewer kind/identifier, model/prompt version when applicable, timestamp, dimension, outcome (`passed`, `failed`, `unresolved`), evidence_refs[], issues, supersedes. Each receipt covers one dimension. |
| Design sidecar | question reference/revision/hashes, design_revision, taxonomy_version, catalogue_version, knowledge_ids, annotation_state, annotator, routes/evidence, representation/objective/checks/misconceptions per taxonomy. Inferred labels remain inferred until an attributed decision. |
| Generation specification | spec_id/revision, curriculum_version, major/grade, scope_id/revision, textbook evidence references, development-only style references, design IDs/revisions, family/constructor version, parameters/constraints, difficulty request, figure specification, model/prompt versions, check plan, split and novelty references. Unknowns hold generation eligibility. |
| Eligibility decision | decision_id, question revision/hashes, purpose, policy version, input receipt IDs, evaluation ID, passed/held, reasons[], timestamp. Derived from evidence; never accept an imported eligible=true flag. |

Review dimensions are extraction/answer association, curriculum, scientific correctness, editorial clarity, figure fidelity, intended difficulty, empirical difficulty and novelty. Human-reviewed is true only with an actual attributable human receipt for the stated dimension. Model agreement cannot create one. Intended difficulty can be reviewed before student data; empirical difficulty remains null. The existing exporter currently asks for difficulty_state=verified; its intended-versus-empirical semantics require explicit later integration, never automatic backfill.

## Correction and invalidation

Append corrections with supersedes links; preserve original PDFs, literal revisions and receipts. Literal/options/figure changes invalidate affected source/science/editorial/difficulty/novelty decisions and vectors bound to old content. Answer mapping changes invalidate answer/science and downstream eligibility. Curriculum/scope changes invalidate affected mappings and purpose eligibility. Design-only changes invalidate dependent generated specifications/evaluations, not source OCR. Schema migrations require explicit versioned adapters and fixtures. Stale evidence stays inspectable but cannot approve a current revision.

## Purpose routing and eligibility

Textbooks establish permitted content; reviewed exams supply design examples; reviewed Maze plans establish weekly scope. Unknown source class/major is held. Keep development and sealed whole-paper/related-variant holdouts disjoint. No holdout in authoring retrieval or tuning. Candidate vectors are searchable only in explicit local evaluation, never implicitly trusted textbook evidence.

`exam_style.py` currently admits extraction-qualified style rows; that is narrower evidence than science approval. Preserve this distinction. `exam_quality.release_eligibility` already checks current content review, source check, curriculum, scientific answer/evidence, issues, difficulty, novelty, vectors and evaluation. Future integration must additionally bind exact source image equality and purpose-specific receipt semantics before claiming the complete contract is enforced.

Generated pool eligibility still requires existing blind solving, audit, verified-booklet and quarantine controls in `mock_generation.py`, `question_quality.py`, `pool_core.py`, question bank and routers. Importing source references must never create a pending_use mock. Weekly ranked uses next reviewed Maze scope with disclosed previous-scope fallback. Preserve atomic claims and per-question quarantine.

## Synthetic fixture envelope

This deliberately incomplete record must be held. It contains no real exam material and is safe for tracked tests. F1 should accept its structural shape but report missing evidence; structural validity and eligibility are separate results.

```json
{
  "schema_version": "0.1",
  "synthetic": true,
  "document": {"document_id": null, "source_sha256": null, "role": "questions", "classification": "mock_exam", "classification_state": "inferred", "exam_id": "synthetic:exam-a", "session": null, "booklet_code": "A", "revision": 1},
  "pairing": {"pairing_id": "synthetic:pair-a", "revision": 1, "question_document_id": null, "answer_document_id": null, "mapping": [], "state": "unresolved"},
  "question": {"question_id": "synthetic:q1", "question_revision": 1, "printed_question_number": 1, "section": "math", "regions": [{"pdf_page": 2, "printed_page": null, "bbox": [0.1, 0.2, 0.9, 0.4]}], "literal_content_sha256": null, "source_image_sha256": [], "figure_sha256": [], "answer_provenance": null},
  "receipts": [],
  "design": {"taxonomy_version": "0.1", "catalogue_version": null, "knowledge_ids": [], "annotation_state": "candidate", "routes": []},
  "eligibility": {"purpose": "authoring_example", "state": "held", "reasons": ["synthetic", "unresolved_pairing", "missing_reviews"]}
}
```

## Private storage and handoff

Real manifests, receipts, crop references, annotations and evaluation outputs live under ignored `backend/data/authoring_work/`, with frozen input references rather than copied secrets. Verify ignore rules per destination. Existing snapshot directories remain immutable. Tracked files contain only synthetic fixtures, schemas and aggregate evidence. No student identifiers, keys, real stems or private screenshots in Git/handoffs. Never import application modules just to validate files: imports may initialize databases/providers.
