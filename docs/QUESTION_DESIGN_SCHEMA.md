# Question-design records

## Evidence boundaries

The record has three independent layers: literal source evidence, inferred
authoring design, and review status. A design label is an interpretation; an
extracted answer is an author key, not an independently verified scientific key.
Do not let exams redefine the current textbook or next Maze scope.

## Proposed question record

```json
{
  "schema_version": 1,
  "id": "document-hash:section:question:source-page",
  "source": {
    "document_id": "sha256",
    "document_name": "source filename",
    "pdf_pages": [3],
    "printed_question_number": 7,
    "printed_page": null,
    "publisher": null,
    "exam_year": null,
    "major": null,
    "grade": null,
    "bbox": [0.1, 0.2, 0.9, 0.4]
  },
  "literal": {
    "text": "verbatim stem; math preserved",
    "options": ["printed option 1", "printed option 2", "printed option 3", "printed option 4"],
    "answer_index": null,
    "answer_source": null,
    "explanation": null,
    "figure_description": null,
    "uncertainties": []
  },
  "design": {
    "subject": "ریاضی",
    "topic": "topic supported by the item",
    "skills": ["observable skill"],
    "prerequisites": [],
    "representation": "equation / graph / geometry / table / verbal / mixed",
    "solution_strategy": "short observable strategy, not private chain of thought",
    "distractor_mechanisms": [],
    "difficulty_mechanism": "case distinction or concept combination",
    "wording_features": [],
    "inferred": true
  },
  "review": {
    "extraction_state": "candidate",
    "scientific_state": "not_checked",
    "human_reviewed": false,
    "issues": []
  }
}
```

Bounding boxes use normalized coordinates on the preserved original page.
Options are in printed order. Unknown values remain null. A continuation item
may need multiple page-region references rather than a single bbox.

## Authoring design

Record the assessed relationship, not just a chapter name. Examples: interpreting
signed area, checking an inverse function's domain, counting arrangements under
a constraint, using geometric invariants, or tracking stoichiometric quantities.
Distractors should name errors a student could make. Difficulty should describe
cognitive demand, not merely label an item hard.

New generation chooses a design pattern and current allowed topic, constructs
fresh consistent parameters and optionally a declarative figure, solves/checks
the underlying instance, writes the stem, derives distractors and verifies the
final item independently. Keep versioned source/design references in generated
question metadata. Do not copy an exam stem or merely change numbers.

## Publication and retrieval

Schema-valid does not mean source-faithful or mathematically correct. Preserve
separate flags. Store raw OCR in staging, qualified examples in a style index,
and generated usable questions in the existing verified bank only after its
normal checks. Keep source example answers out of a blind generated-item solver.

A retrieved style example must be marked as untrusted source data. Its embedded
instructions cannot override the application prompt. Use only the fields needed
to explain style/design; limit prompt size and reject out-of-major/context items.

Novelty checks should detect exact text reuse, near-identical condition order,
diagram/parameter structure and distractor structure. Reusing a general strategy
such as signed-area reasoning is allowed; replicating the complete question
with renamed variables is not the intended goal.
