# بهبود سیستم — RAG، تولید سوال و برنامه‌ریزی (Improvement Workflow)

Status: **living document**. Items marked ✅ are implemented in this working
copy (uncommitted); everything else is a prioritized, actionable plan.

Ground truth for this doc: `backend/app/rag/` (pipeline, hybrid_search,
lexical_search, mock_generation, konkur_format, question_chunks),
`backend/app/routers/boom_ai.py` (weekly planner + today-tests recommender),
`backend/app/rag/pool_core.py` + `scripts/mock_pool_worker.py` (booklet pool),
and the frontend sync layer `frontend/src/homeTasks.ts`.

---

## 1. Architecture snapshot (what exists today)

**RAG:** PDFs → page images (`PDF_PROCESSING_MODE=image`) → CLIP embeddings
(`document_images` collection) + OCR text corpus (`data/ocr`) + structured
`question_bank` chunks → hybrid search (Chroma semantic + in-memory BM25
`LexicalIndex`, RRF fusion) → optional `BAAI/bge-reranker-base` cross-encoder
→ vision LLM (Gemini) reads the *actual* page images → cited answer.

**Question generation:** `generate_booklet` = one LLM call per subject row
(official Sanjesh 1403–1405 format via `konkur_format`), grounded in OCR'd
book excerpts, biased toward weak areas (`WrongAnswer` + recency decay), then
an independent verifier pass (`verify_and_repair_booklet`) re-solves every
question and regenerates broken ones. Pool worker pre-builds booklets per
(major, difficulty) so students never wait on a live generation.

**Planning:** `weekly-plan` = LLM JSON blocks + deterministic
`_default_week_plan` fallback + `_complete_week_plan` validator (fills all 7
days, honors protected static slots ✅). Weakness memory drives concrete
«تست‌های ۴۱ تا ۵۶، صفحه …» range titles. The Home to-do list is derived from
the plan and writes completion back (✅ this working copy).

---

## 2. Bugs found & fixed in this pass (✅, with regression tests)

| # | Bug | Fix |
|---|-----|-----|
| 1 | `pad_booklet` spread answer keys by *re-indexing* without moving option text → silently wrong keys | Swap the option strings (`0 ↔ target`); keys stay correct (`tests/fix_regressions_test.py`) |
| 2 | `_complete_week_plan` backfill passed `_occupied_slots([])` (always empty) → default blocks could land on protected class slots | Pass the real `occupied` list through |
| 3 | `catalog_parser_test` hard-failed on any machine without the gitignored scan corpus | `skipif` when `test-books/*.txt` absent |
| 4 | BM25 recomputed IDF per chunk×term and scanned every chunk per query | Precompute IDF per unique term; score only matching chunks (ranking preserved, verified) |
| 5 | Fallback weekly plan placed blocks into free slots only now, and alternates study/test emphasis weekly (`week_offset` parity) | Passed `occupied` + `week_start.isocalendar()[1] % 2` |
| 6 | Persian stopwords («و، در، از، به، …») indexed & scored as content terms | Stopword filter in `tokenize` (affects index & query symmetrically) |

Earlier the same day (context): login phone normalization, SMS proxy
bypass/retry/failover, Home↔plan sync.

---

## 3. RAG improvements (prioritized)

- **P0 — Golden set before any retrieval change.** Build
  `scripts/eval_rag.py`: ~50 exam-style questions with expected
  (book, page) targets from the OCR corpus; report recall@k for semantic,
  lexical, hybrid, and hybrid+rerank. No change merges without before/after.
- **P1 — OCR coverage.** `ocr_corpus` is resumable with a daily cap — run it
  to completion. Add a small admin endpoint reporting pages-OCR'd / total per
  book; planner range titles and generation grounding both depend on it.
- **P1 — Persian lexical quality.** ✅ stopwords done; next: a small
  synonym/inflection map in `normalize_text` (مشتق/مشتق‌گیری, تست/سوال,
  نمودار/نمودارها) — keep it auditable (a literal dict, not a model).
- **P2 — Embedding upgrade path.** CLIP's text tower is weak on Persian.
  Benchmark `paraphrase-multilingual-MiniLM` (or BGE-M3) for the text side on
  the golden set; keep CLIP for page images. Embeddings are versioned in
  Chroma metadata — re-ingest behind a flag.
- **P2 — Reranker model.** `bge-reranker-base` is EN/ZH-centric; swap to
  `BAAI/bge-reranker-v2-m3` (multilingual) behind `RERANK_MODEL_NAME` and
  measure on the golden set.
- **P3 — Feedback signal.** Log retrieval hits + 👍/👎 per chat answer;
  review weekly, feed systematic misses back into the synonym map.

## 4. Question generation improvements

- **P0 — ✅ Safe answer spreading** + add a distribution warning in the
  verifier (any option >40% → log).
- **P1 — Verifier diversity.** The verify pass uses the *same* pool LLM that
  wrote the question; a model that mis-keyed it may "verify" it wrong too.
  Add `VERIFIER_PROVIDER` (e.g. Cerebras verifies Gemini-generated booklets)
  and route `_verify_question` through it.
- **P1 — Dedupe.** Add an exact/normalized-text duplicate detector in
  `parse_booklet` (drop dupes before `pad_booklet`), and sample topics
  without replacement across regeneration attempts.
- **P1 — Grounding hygiene.** `retrieve_book_context` should drop chunks that
  literally contain another option's text (leak), and raise `per_subject`
  for weak-area rows.
- **P2 — Difficulty calibration.** Track empirical wrong-rate per topic from
  attempts; map to the existing 3 `_DIFFICULTY_LABEL` buckets in the prompt.
- **P2 — Figure questions.** Store the source page-image id on question rows
  so the client can render figure-dependent questions (schema + UI).
- **P3 — Cost ops.** Nightly pool restock across all shelves; alert when a
  (major, difficulty) shelf depth < 2.

## 5. Planning improvements

- **P0 — ✅ Protected slots + fallback placement + weekly alternation.**
- **P1 — Completion feedback loop.** Home to-do completion (persisted per
  day) should reach the weekly-plan prompt as «هفته قبل: X از Y انجام شد» —
  aggregate `homeTasks:*` stores server-side in the request payload.
- **P1 — Spaced repetition.** The today-tests recommender is recency-biased;
  add intervals (1/3/7/14 days since the topic was last practiced) on top of
  the weakness weights.
- **P2 — Konkur-countdown pacing.** Scale weekly test counts from
  `KONKOOR_DATE` + remaining syllabus (book catalog ranges) instead of a
  fixed `study_h` multiplier.
- **P2 — Transparency.** When the validator drops LLM blocks over protected
  slots, list them in `response.note` so the UI can say *why*.
- **P3 — iCal export** of the weekly plan.

## 6. Engineering workflow (how to land these safely)

1. **Golden set first** — retrieval/prompt changes ship with numbers.
2. **One change per PR**, toggled by response fields (`llm_used`,
   `reranker` flag) so you can A/B in production logs without redeploys.
3. **Every bug fix lands with a regression test** (pattern:
   `tests/fix_regressions_test.py`).
4. **Version the prompts** (`_GENERATE_PROMPT` v2, …) and stamp the version
   onto generated booklet rows for later quality analysis.
5. **Weekly ops:** pool worker nightly → check shelf depth; `ocr_corpus`
   until complete; skim 429/503 provider logs (SMS/LLM) for flakiness.
6. **Rollout order:** eval script → stopwords/synonyms → reranker swap →
   verifier split → planner feedback loop.

## 7. This PR vs next

✅ **Now (uncommitted):** the six fixes in §2 + regression tests + lexical
perf + fallback placement.
**Next PR (pick one):** golden-set eval script · synonym map ·
`VERIFIER_PROVIDER` split · plan-completion feedback loop.
