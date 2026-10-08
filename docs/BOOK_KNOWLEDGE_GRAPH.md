# Book-sourced knowledge graph

Lesson titles come from the shared promoted book OCR under `backend/data/ocr`,
not a fixed curriculum or the model's remembered syllabus. The extraction
accepts a title only when its heading quote matches a supplied book page.
Each lesson keeps its book name and PDF page number. Grade assignments also
require a cited grade label; combined books without lesson-level grade
evidence stay in the unknown/combined column.

Run from `backend`, with its normal ignored `.env` and chat provider:

```bash
python -X utf8 scripts/build_knowledge_graph.py
```

The model extracts headings in small batches. Requests are paced by default
to respect the provider's per-minute allowance. `--request-interval 30` slows
the job; `--limit 2` processes at most two uncached books. Completed books are
cached and reused on the next run. A provider refusal stops new requests and
preserves previously extracted books. Resume after the provider's retry
period. `--no-prerequisites` extracts titles without estimating lesson links.
`--cached-only` assembles already extracted books and resumes cached prerequisite
inference without requesting another extraction of incomplete books.
`--model MODEL_ID` selects a provider-supported model for this job only;
it does not edit the site's chat/planner model settings.

The output lives in the ignored `backend/data/knowledge_graph/` directory.
Transfer `catalog.json` separately to the VM, just like the shared OCR and
vectors. The optional `KNOWLEDGE_GRAPH_PATH` setting changes that location.
Raw PDFs and another embedding pass are not required.

Opening `/api/insights/knowledge-graph` reads this cached catalogue only: it
does not invoke a provider. The endpoint filters books by major and overlays
only the authenticated student's completed study sessions and answers.
Exact normalized lesson names link evidence to nodes; unmatched topics do
not grant mastery to unrelated lessons. Missing book coverage yields an
explicit empty/partial graph rather than synthetic fallback topics.

Prerequisite links and importance scores are model estimates, visibly
labelled as such. Links cannot introduce nonexistent lessons, cycles,
incompatible majors or a later known grade as a prerequisite for an earlier
grade. Book order alone does not lock an unrelated lesson. Scanned-source
coverage is not a guarantee that every official textbook chapter has been
recognized: incomplete OCR must be improved and the extraction rerun.
