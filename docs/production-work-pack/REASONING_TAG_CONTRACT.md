# ST reasoning annotation contract — draft 0.1

22 October 2026. Implementation: backend/app/rag/reasoning_tags.py, pure stdlib and no application imports. Existing question_design.py and its records are unchanged. Registry mirrors QUESTION_REASONING_TAXONOMY.md; a test detects drift. Vocabulary remains candidate pending HT human calibration.

## Freebuff usage

```python
from app.rag.reasoning_tags import validate_annotation
result = validate_annotation(record, catalogue=current_nodes,
    catalogue_version=frozen_catalogue_sha256, question=current_question_binding)
```

Load the catalogue explicitly from an approved local snapshot. Do not import book_curriculum or app startup merely to validate: those resolve configuration. current_nodes is its list of nodes; each referenced node must have sources. Supply the exact catalogue snapshot hash as catalogue_version. Caller is responsible for selecting the actual current catalogue; this validator cannot authenticate a caller-supplied catalogue.

current_question_binding has question_ref, question_revision and source, exactly as in the fixture. Source includes document_id (PDF SHA), document_revision, content_sha256 and ordered figure_sha256 list. Missing hashes remain null with holds. Binding requires equality of the whole source object; changed figures, source or question revision invalidate stale annotations. Without a current binding result carries current_question_not_bound. The validator reads/writes no files and mutates no input.

The authoritative synthetic example is tests/fixtures/reasoning_tags/candidate.json. Required root fields are shown there. Compared with the conceptual taxonomy example, this sidecar adds annotation_revision, question_revision, document revision, explicit annotator identifier, knowledge_evidence and unresolved_labels. It preserves existing source IDs; no automatic conversion or bulk annotation occurs. A future adapter must be versioned and reviewed separately.

knowledge_evidence entries carry knowledge_id, source (an exact source dictionary from that node) and short evidence connecting the question to it. Empty knowledge arrays are valid unresolved records and stay held. Nonexistent nodes, mismatched catalogue versions and invented source citations are errors. Source membership validates provenance structure, not the truth of the explanation.

Route role: primary/alternative. Within a route, technique role: primary/supporting/check. Check/shortcut entries reference a route. Representations specify given/constructed/requested. Misconceptions require an ordered zero-based option index and concrete evidence. Unresolved labels carry axis and reason. Evidence is a nonempty string up to1500 characters; it should be a checkable equation/condition/region statement, not private reasoning. Structure checks cannot determine whether evidence is scientifically sound.

Annotations retain annotator kind, identifier, actual model and prompt version. A human annotator may use null model/prompt; recording authorship alone is not a human approval. Intended difficulty is nullable or easy/konkur/hard/extreme plus rationale. Empirical difficulty is null in this draft contract: importing student statistics requires its own later contract. No difficulty or student weakness is computed from tags.

## Results and review boundaries

Return valid, errors[{path,code}], holds[] and eligible=false. valid means structural/reference checks pass only. All records carry draft_vocabulary/not_approval holds. Review states allowed here are candidate/unresolved annotation, candidate/synthetic/unresolved source, not_checked/unresolved science, human_reviewed=false, eligibility=held. Actual human/scientific receipts are separate records and must be integrated in SR; this endpoint cannot promote records. Imported claims of approval are rejected.

Keep raw model outputs separately and validate parsed candidate sidecars before review. This module does not certify OCR, scientific correctness, evidence quality, novelty, catalogue authenticity or curriculum applicability. Unknown new labels belong in unresolved entries and separate registry-change proposals. Shared registry changes require version/alias/migration decisions; never silently rewrite existing records. annotation_revision increases when the annotation changes; source/question revisions change only when their respective evidence changes. The validator checks positive revisions, not historical monotonicity: the eventual store must enforce append-only history.

## Checks and next handoff

Command from repo root (with PYTHONPATH=backend): backend/.venv/Scripts/python.exe -X utf8 -m pytest tests/reasoning_tags_test.py tests/question_design_test.py tests/exam_source_packets_test.py -q --no-header -p no:cacheprovider

Actual result: 26 passed. Covers malformed structures, invalid versions/roles, missing evidence, nonexistent/unbacked knowledge, stale bindings, invented catalogue sources, approval spoofing and preservation of input. No provider calls or real questions were annotated.

Freebuff F2 is now unblocked by ST: use the fixture and validation result shape for the isolated review component at its assigned paths. Do not wire routers or change shared schemas. F3 still requires H2. HA still requires H2 and should produce independent candidate records. F1 ownership remains unchanged.
