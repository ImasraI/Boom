# PDF to answers, generated questions and weekly plans

Code walkthrough checked 29 October 2026. Distinguish the current local working
tree from deployed commit 2e2b895: the recent deployment shipped account access,
arena names and historical answer sheets, not the unfinished authoring/RAG work.
This document describes code paths, not a fresh live health or corpus audit.

## 1. Ordinary website document upload

Entry: `POST /api/documents/upload`, `backend/app/routers/documents.py`.
Authentication supplies the user ID. Extension/size checks run and the original
is saved under the configured UPLOAD_DIR/user ID with a sanitized filename.

The route branches on PDF_PROCESSING_MODE:

- Text mode: `rag/loaders.py:extract_text` -> `utils/pdf_converter.py:pdf_to_text`.
  PyMuPDF reads a text layer. Its scanned-page fallback currently uses local
  Ollama/qwen2.5vl; this is **not** the separate free-tier Gemini scanning fleet.
  Missing local services can therefore break that fallback.
- Text then enters `rag/pipeline.py:ingest_document`/`_ingest_document` ->
  `rag/chunking.py:chunk_text` -> `rag/embeddings.py:get_embedding_model` ->
  `embed_documents` -> `rag/vector_store.py:add_chunks`. It refreshes the user's
  lexical search index via `HybridSearch.refresh`.
- Image mode: `pipeline.py:ingest_pdf_as_images` ->
  `rag/image_loader.py:pdf_to_page_images` -> `rag/image_embeddings.py` ->
  the separate image vector store. `utils/storage.py` retrieves image bytes
  from the configured storage. Page images remain separate from their vectors.

The plain text route splits by sentence-aware boundaries/size/overlap; it is not
the structured parent-question chunking used for the reviewed exam candidates.
Ordinary upload does not establish exam identity, answer pairing, curriculum
approval or authoring eligibility.

## 2. Bulk books/exams and structured local scanning

The root `mocks/` corpus is distinct from uploading through the website.
`START-EXAM-WORKERS.cmd` starts `backend/scripts/run_exam_scan.cmd`, which invokes
`scripts/import_exam_examples.py scan`. The same Python driver offers inventory,
native extraction, benchmarking, status and standardization modes.

Relevant modules:

1. `rag/exam_inventory.py`: inventory PDFs/archives while preserving originals.
2. `rag/exam_corpus.py`: source hashes, page text/images, stable artifacts,
   checkpoints and safe paths.
3. `rag/exam_scanning.py`: structured page extraction, schema checks, visual
   references and candidate standardization.
4. `rag/exam_vision.py`, `exam_network.py`, `exam_control.py`: existing free
   credentials, provider/network availability, per-key refusal state, stop/resume
   and checkpoint control. Workers are execution slots, not guaranteed quotas.
5. `rag/exam_source_packets.py`: question/answer pairing using confirmed source
   identity and printed numbering. Never array-position matching.
6. `rag/authoring_review.py`, `routers/authoring_review.py`,
   `frontend/src/authoringReview/`: source images, review packets and version-bound
   decisions. Transcription, answer correctness and editorial judgment differ.
7. `rag/exam_quality.py`: quality issues, parent/child retrieval chunks, revision
   comparisons and export eligibility. Smaller retrieval children retain their
   parent question rather than becoming separate questions.
8. `scripts/stage_exam_embeddings.py`: resumable candidate-vector staging in
   `exam_ocr_candidates`, bound to a frozen snapshot/model/dimensions. Embedding
   completion alone does not activate these records for runtime retrieval.

Main private artifacts live in `backend/data/exam_examples/` and
`backend/data/authoring_work/`. Other processed book OCR/images/catalogues live
under their configured backend data paths. `rag/ingest_raw.py` provides a separate
batch importer for configured raw PDFs, including page-image ingestion; it is not
the reviewed exam-authoring promotion pipeline.

## 3. Storage roles

- Original PDF: source evidence and possible reprocessing.
- Page image: visual evidence for equations, diagrams, tables and layout.
- OCR/structured JSON: extracted content, question boundaries and provenance.
- Text/image embeddings: numeric representations used to find relevant content.
- Chroma: document, structured question-text and image-vector collections.
- SQLite `backend/rag_data.db`: accounts, profiles, calendar, question bank,
  generated booklets, attempts, reports and learning history.
- Review/policy sidecars: revision-bound decisions and source eligibility.

Chroma's question-text collection is not SQLite's `bank_questions` table. The
former retrieves passages; the latter holds selectable test questions.
API keys identify access; none of these ingestion steps train their model weights.

## 4. Chat response path

`frontend/src/pages/Chat.tsx` -> `POST /api/boom/chat` ->
`backend/app/routers/boom_ai.py:boom_chat` ->
`backend/app/rag/pipeline.py:answer_question`.

The router supplies authenticated student/calendar context and handles structured
homework/plan actions. Inside the pipeline:

1. An applicable "today's tests" request can use its dedicated book-range
   recommender. Simple messages can skip retrieval entirely.
2. `rewrite_query` produces a search query; `embeddings.py` embeds it.
3. `_assemble_retrieval` searches books, structured question text and optionally
   page images; it deduplicates evidence and resolves referenced image files.
4. `hybrid_search.py` offers vector search plus BM25 lexical search, reciprocal
   rank fusion and optional cross-encoder reranking from `reranker.py`.
5. Explicit-purpose calls in the local work branch use `source_routing.py` to
   filter role, major, curriculum, split and reviewed scope **before ranking**.
   This policy-aware branch has its own scoped search path; do not assume it
   executes every stage of the legacy hybrid path. Unactivated sources stay held.
6. `_build_messages`/`_build_image_messages` assemble the user query, history,
   permitted context and retrieved text/images. The selected client in `llm.py`
   generates the answer. Missing images can fall back to text; missing semantic
   vectors can leave the ordinary hybrid path using lexical retrieval.
7. The response includes answer text, source references and confidence metadata;
   these are not a guarantee of correctness. The frontend's `ChatMarkdown`
   component renders Markdown/math. Retrieval tracing records stages for the
   admin inspector (`rag/trace.py`, `frontend/src/components/RagInspector.tsx`).

The LLM sees selected text/image context, not the entire corpus or raw vectors.

## 5. Practice mocks and generated question pool

`frontend/src/pages/Mock.tsx` -> `frontend/src/mockGeneration.ts` ->
`routers/mocks.py` generation-job endpoints / `_generate_reserved_mock`.

The first choice is already verified stock: `rag/question_bank.py:assemble`, or
an eligible pooled booklet through `_claim_pool_mock`. The normal UI requests
stock-only generation: it assembles available questions rather than necessarily
calling an LLM. Stock shortages must be reported; live fallback requires the
request/settings to allow it.

Background generation is driven by `scripts/mock_pool_worker.py` and the
`rag/pool_service.py`/`pool_core.py`/draft-queue code. It calls
`rag/mock_generation.py:generate_booklet`:

- Build the subject/count/topic specification.
- Retrieve relevant book context, or use the book-grounded branch where required.
- Generate structured questions through `llm.py`; parse text, four options,
  answer, explanation and typed figure. Legacy paths can fall back to model
  knowledge when retrieval is absent; this is a quality gap, not book grounding.
- `verify_and_repair_booklet` performs separate answer-withheld verification,
  repairs/replacements and rejects unresolved items. Model agreement is not
  human mathematical approval.
- Store eligible questions in SQLite `bank_questions`; booklet JSON in
  `generated_mocks` refers to bank IDs. Reports mark questions corrupt for future
  selection. Completed attempts retain their original result snapshots.

Ranked routing uses `rag/weekly_ranked.py` for Maze scope/eligible stock, then
`routers/arena.py` handles matchmaking, serving and scoring.

## 6. Weekly plan

`frontend/src/pages/Schedule.tsx` -> `POST /api/boom/weekly-plan` ->
`routers/boom_ai.py:generate_weekly_plan` -> `planner/adaptive.py:build_week`.

This current endpoint returns `llm_used: false`:

1. Read the server-owned profile, results/weakness evidence, homework, progress,
   available time and current calendar.
2. `planner/calendar.py` expands repeating activities, preserves protected/manual
   blocks and checks calendar-version conflicts/fixed-block overlaps.
3. `planner/mock_outline.py:next_mock_outline` reads processed Maze schedule
   caches and selects the next relevant dated scope. A PDF merely present on
   disk is not sufficient if its schedule extraction/cache is missing.
4. `planner/resources.py` reads available book/OCR evidence and numbered topic
   ranges; student mistakes and progress affect prioritization and allocation.
5. `planner/engine.py:generate_plan` fits candidate work into free slots;
   `validate_plan_items` checks schedule constraints.
6. `assign_test_resources` assigns book, question_start/question_end and page
   ranges, avoiding already reserved/completed ranges. Missing evidence produces
   warnings, not invented test numbers.
7. Persist TaskProgress/calendar records; return blocks, warnings and unscheduled
   work. The frontend renders the calendar. Chat can propose separate changes,
   but this does not make the weekly endpoint a free-form LLM schedule writer.

## 7. The 24-question local experiment is a separate path

Reviewed summaries -> `prepare_authoring_benchmark.py` freezes task briefs ->
`run_authoring_benchmark.py` calls Gemini with one exact abstract task prompt ->
`authoring_benchmark.py` parses and checkpoints the candidate -> independent
mathematical checks and `solve_benchmark_blind.py` -> versioned review pages.

No raw exam PDFs/answers were supplied to that experiment. Its 24 drafts are not
automatically production bank questions. Human editorial feedback is pending;
formal taxonomy annotations have not been assigned to this batch. Broader
authoring integration, source eligibility and release gates remain incomplete.

## Debugging by symptom

| Symptom | First boundary to inspect |
| --- | --- |
| Garbled equations or absent options | Page image versus OCR/transcription, before embeddings |
| Good OCR but irrelevant chatbot passages | Source eligibility, query, retrieval rankings, reranker and filters |
| Right passage but wrong explanation | Actual assembled prompt and returned LLM answer |
| Missing diagrams | Stored image key/file, image retrieval and vision client, not just text vectors |
| No practice questions available | Verified active SQL stock and exact scope/grade/count filters |
| Bad generated questions despite valid JSON | Grounding/design specification and independent validation |
| Wrong Maze topics or missing mock date | Processed schedule cache, dates and student major/grade |
| Plan lacks numbered tests | Book/OCR topic ranges and previous allocations |
| Not enough scheduled study | Free slots, protected events, workload feasibility and unscheduled warnings |
