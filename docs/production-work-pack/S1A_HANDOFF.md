# S1a completed source-packet preparation — 22 October 2026

Scope: local source records, explicit question/answer associations, review packets and proposed splits only. H1 approval and S1b routing remain separate. S1a completion means review packets prepared, not transcription/scientific approval.

## Implementation and evidence

New reusable CLI backend/scripts/prepare_maze_source_packet.py supports only the exact H0 PDF hash. It rejects other PDFs instead of applying guessed section/range rules. It uses existing digest/atomic_json/packet APIs and never edits inventory snapshots or live indexes. It independently detects the complete printed sequences 1..105 in question pages2..21 and worked-answer pages26..88. Covers1/8/23 establish the combined exam identity; cover8 explicitly gives physics41..75 and chemistry76..105, while cover1 gives math1..40. This booklet therefore has 40 math,35 physics,30 chemistry items. Global numbering is preserved. Subject is source-booklet attribution, not a new curriculum mapping.

Association uses explicit identities through pair_questions, not array offsets or filenames. Region references include PDF page, normalized crop bbox, rendering engine/scale and exact crop image SHA256; native text and region metadata bind content hashes. Per-item IDs remain compatible with existing SHA:page:number parents; answer sidecars have :answer suffix. Original PDF, prior packets and frozen vectors are preserved.

Private output: backend/data/authoring_work/s1a-mapped/status.json points to the immutable current packet. It contains 105 question regions/records,105 worked-answer records,105 unique author-key candidates and105 publisher label candidates. All105 pairs have shared Persian stem evidence. Raw publisher labels remain attributed native candidates; their codes are not invented lesson IDs or mapped to our difficulty scale. Authors' keys are not scientific verification.

65 mappings remain held for multi-page continuation boundary review;40 are linked_candidate. All records remain ineligible. Multi-page extraction uses conservative page regions that may retain headers/footers; these are review crops, not a claim of precise figure segmentation. No full-source scientific or transcription approval exists. This explicit review queue is a delivered packet, not an incomplete silent association. Further region decisions belong to source-review integration and H2; H1 may reject/revise proposed scope/splits.

Assistant visually compared distributed boundary crops for questions1,40,41,75,76,105 and corresponding answers. Private boundary-review.png records that inspection; it is not a human receipt. Other mappings have mechanical printed-number/key/stem checks, not claimed visual approval. Source reviewed count remains0, scientific reviewed count0. No source text was committed to tracked fixtures/reports.

## Reproduction

From repo root:

```powershell
backend/.venv/Scripts/python.exe -X utf8 backend/scripts/prepare_maze_source_packet.py C:/Users/Arsam/Desktop/26-Maze-070403.pdf backend/data/authoring_work/s1a-mapped
$env:PYTHONPATH='backend'
backend/.venv/Scripts/python.exe -X utf8 -m pytest tests/maze_source_packet_test.py tests/exam_source_packets_test.py tests/reasoning_tags_test.py -q --no-header -p no:cacheprovider
```

Actual tests:25 passed,5 PyMuPDF/SWIG deprecation warnings. Tests cover sequence gaps/reordering/decoys, unknown PDF refusal, explicit booklet/session/section mismatch, ambiguous keys, continuations, stale receipts and revision preservation. Run uses native PDF reads and local renders only; no provider/credential access, OCR jobs, embedding, migrations or VM calls. No existing worker was stopped or started.

## Next handoff

H1: review curriculum version and split candidates after F1 is accepted. This already-exposed Maze paper is proposed for development, never an unseen final holdout. Whole-paper duplicate/compilation and family checks are explicitly pending; no split is frozen as approved. The grade is unknown rather than inferred.

SR/H2: review conservative multi-page boundaries and exact source/answer crops; record attributed receipts bound to both source and content/image hashes. Preserve publisher difficulty/type/code labels independently of inferred reasoning labels and scientific evidence.

Freebuff F1: repair its test harness/path problems from the Phase1 audit, then Sol reviews its patch. It was not integrated or edited in this S1a continuation. Phase1 overall still waits for accepted F1. ST remains complete.
