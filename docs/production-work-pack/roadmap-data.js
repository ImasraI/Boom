window.ROADMAP_DATA = {
  "version": "karzar-roadmap-v1",
  "checkedAt": "2026-10-22T12:44:44.451747+00:00",
  "stage": "Source qualification and reasoning-label design",
  "notice": "Saved-evidence snapshot, not a live worker monitor. Future task completion is manually reported; this page never runs agents, approves questions or deploys code.",
  "milestones": [
    {
      "title": "Frozen candidate embeddings",
      "state": "complete",
      "detail": "17605 / 17605 stored vectors; 4824 question pages. Candidate OCR, not a reviewed bank.",
      "evidence": "backend/data/exam_staging/batch-5000-v1/embedding-status.json"
    },
    {
      "title": "Retrieval pilot",
      "state": "limited",
      "detail": "6 queries; 3 source questions. Not representative enough for release.",
      "evidence": "backend/data/exam_staging/batch-5000-v1/retrieval-pilot.json"
    },
    {
      "title": "Release readiness",
      "state": "blocked",
      "detail": "Saved release gate remains blocked. Required source, curriculum, science, difficulty and novelty reviews are outstanding.",
      "evidence": "backend/data/exam_staging/batch-5000-v1/release-readiness.json"
    },
    {
      "title": "Prompt pack and taxonomy",
      "state": "draft",
      "detail": "Instructions are available. Contracts, source pairing and human review have not been evidenced as complete by this roadmap.",
      "evidence": "docs/production-work-pack and docs/QUESTION_REASONING_TAXONOMY.md"
    }
  ],
  "phases": [
    {
      "id": 0,
      "title": "Start here"
    },
    {
      "id": 1,
      "title": "Source and tag contracts"
    },
    {
      "id": 2,
      "title": "Scope and reviewer interface"
    },
    {
      "id": 3,
      "title": "Integrate trusted inputs"
    },
    {
      "id": 4,
      "title": "Integrate review decisions"
    },
    {
      "id": 5,
      "title": "Review original questions"
    },
    {
      "id": 6,
      "title": "Independent annotation and tests"
    },
    {
      "id": 7,
      "title": "Compare model labels"
    },
    {
      "id": 8,
      "title": "Approve vocabulary"
    },
    {
      "id": 9,
      "title": "Construct new questions"
    },
    {
      "id": 10,
      "title": "Verify and preserve"
    },
    {
      "id": 11,
      "title": "Prepare quality comparison"
    },
    {
      "id": 12,
      "title": "Expert judgment"
    },
    {
      "id": 13,
      "title": "Integrate student experience"
    },
    {
      "id": 14,
      "title": "Independent QA"
    },
    {
      "id": 15,
      "title": "Pilot candidate"
    },
    {
      "id": 16,
      "title": "Student pilot"
    },
    {
      "id": 17,
      "title": "Freeze and evaluate"
    },
    {
      "id": 18,
      "title": "Release decision"
    },
    {
      "id": 19,
      "title": "Deploy"
    },
    {
      "id": 20,
      "title": "Public checks"
    },
    {
      "id": 21,
      "title": "Accept and iterate"
    },
    {
      "id": 22,
      "title": "Later improvements"
    }
  ],
  "tasks": [
    {
      "id": "S0",
      "title": "Establish contracts and file ownership",
      "owner": "Sol",
      "phase": 0,
      "priority": "P0",
      "deps": [],
      "summary": "Give the three workers one compatible specification and a shared baseline.",
      "deliverables": [
        "CONTRACTS.md with synthetic records",
        "TASK_BOARD.md with owners and writable paths"
      ],
      "acceptance": [
        "Existing modified and untracked code accounted for",
        "No overlapping writes or assumed approvals"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S0: Establish contracts and file ownership\n\nYou are the technical lead and sole integrator for Karzar/Boom in\nC:\\Users\\Arsam\\Desktop\\Boom-merged. Read AGENTS.md and\ndocs/production-work-pack/README.md plus its required source documents.\nExecute S0 only now; prepare later stages without starting them.\n\nInspect the dirty working tree, including untracked files, current source/import\nformats, review gates, retrieval routing, question generation and pool selection.\nPreserve all existing work. Confirm documented status from saved evidence; do\nnot trigger scans, embedding, paid calls, database migrations or provider probes.\n\nCreate docs/production-work-pack/TASK_BOARD.md and CONTRACTS.md. Define the\nsmallest contracts needed for separate question/answer PDFs, source classification,\nreview receipts, design records, generation specifications and eligibility.\nInclude source SHA, exam/session/booklet identity, printed question number,\npage/crop references, content/image hashes, answer provenance, curriculum version,\ninferred-vs-confirmed labels and independent review dimensions. Unknowns are null.\nDistinguish schema versions from document/question revisions. Define immutable\nIDs and correction/invalidation rules. Do not replace existing compatible formats.\n\nList writable files for yourself and Freebuff, plus task dependencies. Freebuff\nF0 leaves application code unchanged and can write its handoff immediately. Assign its new helper/test paths before\nF1-F3. Specify how private artifacts are stored and referenced without secrets.\nPublish small synthetic example records so Freebuff can work without live data.\n\nSet an initial scoped pilot and a predeclared evaluation protocol with human\ninput still pending where necessary. List real gaps, not every hypothetical\nimprovement. Identify obsolete statements in old docs without bulk cleanup.\n\nDeliver the board, contracts, exact F1 starting instruction, known blockers and\nthe README handoff. No push, VM work or production activation.",
      "source": "SOL_PROMPTS.md / S0",
      "optional": false
    },
    {
      "id": "F0",
      "title": "Inspect gaps and prepare the first helper",
      "owner": "Freebuff",
      "phase": 0,
      "priority": "P0",
      "deps": [],
      "summary": "Inspect the existing system and report specific gaps without changing core code.",
      "deliverables": [
        "FREEBUFF_HANDOFF.md",
        "Small synthetic failure scenarios"
      ],
      "acceptance": [
        "Claims distinguish observation from old documentation",
        "Next helper files proposed to Sol"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK F0: Inspect gaps and prepare the first helper\n\nWork in C:\\Users\\Arsam\\Desktop\\Boom-merged. Read AGENTS.md and\ndocs/production-work-pack/README.md. You are the bounded tooling/QA worker.\nExecute F0 now, without changing application code or starting provider jobs.\n\nInspect existing inventory/import, quality viewer, tests and documentation. Read\ngit status and preserve every existing change. Do not read or print private keys.\nList what already works, concrete gaps, and candidate new files you can own without\ncolliding with Sol. Focus on question/answer PDF associations, evidence display,\nfailure recovery and reviewer usability. Distinguish saved historical results from\ncurrent observations. Do not treat a README checklist as verified implementation.\n\nWrite only docs/production-work-pack/FREEBUFF_HANDOFF.md with your findings,\nproposed F1-F3 files, commands actually run and exact next step. Do not modify the\nshared TASK_BOARD or contracts. If Sol's contracts are not ready, report that\ndependency and prepare synthetic test scenarios; do not invent incompatible APIs.",
      "source": "FREEBUFF_PROMPTS.md / F0",
      "optional": false
    },
    {
      "id": "H0",
      "title": "Identify one exam and its answer booklet",
      "owner": "You",
      "phase": 0,
      "priority": "P0",
      "deps": [],
      "summary": "Start with one complete, traceable exam; classify remaining source files afterward.",
      "deliverables": [
        "Source pairing record with year/session/major",
        "Uncertain matches listed"
      ],
      "acceptance": [
        "Printed numbering and distributed samples agree",
        "Unknown identities remain unresolved"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK H0: Identify one exam and its answer booklet\n\nClassify each document as current textbook, official exam, reputable mock, answer booklet, compilation or unknown. Record filename, document SHA256, publisher where known, subject, grade/major, edition/year/session, printed numbering and PDF page references. Sol can provide hash extraction; do not manually invent identifiers.\n\nPair question and answer PDFs using matching exam identity, session/version, question counts and printed numbers. Check a few distributed questions, including numbering resets and combined sections. Preserve competing matches as unresolved; filenames alone do not establish a match. A printed answer is an **author-provided key**, not scientific verification.\n\n**Handoff:** source manifest, proposed pairings, supporting page references and unresolved cases. Unknown facts stay null or explicitly unknown. Preserve originals and record corrections separately.",
      "source": "HUMAN_TASKS.md / H0",
      "optional": false
    },
    {
      "id": "S1a",
      "title": "Create source packets and pairing contracts",
      "owner": "Sol",
      "phase": 1,
      "priority": "P0",
      "deps": [
        "S0",
        "H0",
        "F0"
      ],
      "summary": "Make the chosen question/answer pair inspectable and handle ambiguous numbering.",
      "deliverables": [
        "One source-bound development packet",
        "Versioned pairing and correction rules"
      ],
      "acceptance": [
        "Question IDs use source identity and printed numbers",
        "Ambiguous joins are held"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S1a: Create source packets and pairing contracts\n\nSCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\nImplement source records and question/answer pairing only. Use H0's chosen exam. Prepare review packets and split candidates; final curriculum/split approval and retrieval integration happen in H1/S1b.\n\nBROADER STAGE REFERENCE:\nExecute S1 using the S0 contracts and human H0-H1 source decisions. If any human\ndecision is absent, implement the schema and synthetic tests while holding the\naffected real source. Integrate Freebuff F1 only after reviewing its patch.\n\nExtend existing inventory/imports to link questions.pdf with answer-key.pdf and/or\nworked-solutions.pdf by confirmed exam/session/booklet identity and printed\nquestion number. Detect missing, repeated, conflicting and offset numbering,\nmulti-exam solution files, page continuations and ambiguous booklet variants.\nNever zip questions and answers by array position or filename alone.\n\nKeep source evidence, inferred design and scientific review independent. Preserve\noriginals and frozen snapshots; corrections produce versioned deltas. Bind answer\nand transcription receipts to their source and content hashes.\n\nImplement explicit retrieval purposes: authoring designs from eligible exam\nexamples; factual grounding from current textbooks; weekly plan scope from Maze\nplus test-book ranges and student data. Apply role, major, curriculum and split\nfilters before ranking. Unknown sources and unreviewed candidates cannot become\ntrusted evidence through a broad fallback. Old exam topics cannot expand scope.\n\nFreeze development and final-evaluation splits, including duplicate originals\ninside compilations and close question-family variants. Protect holdout answers\nfrom authoring prompts and blind solvers. Record retrieved IDs and filter reasons.\nTest cross-role leakage, stale reviews, ambiguous answer joins and missing scope.\nReturn measured coverage and unresolved source mappings; do not bulk approve data.",
      "source": "SOL_PROMPTS.md / S1",
      "optional": false
    },
    {
      "id": "F1",
      "title": "Build the offline source validator",
      "owner": "Freebuff",
      "phase": 1,
      "priority": "P0",
      "deps": [
        "S0",
        "F0"
      ],
      "summary": "Validate metadata, image references and review hashes without modifying the corpus.",
      "deliverables": [
        "Read-only validator CLI",
        "Synthetic pairing/hash/path tests"
      ],
      "acceptance": [
        "No provider requests or automatic approvals",
        "Valid and malformed fixtures give expected findings"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK F1: Build the offline source validator\n\nExecute F1 after Sol has published CONTRACTS.md and assigned your files.\nSuggested ownership: backend/scripts/validate_exam_review_inputs.py and\ntests/exam_review_inputs_test.py. These are proposed new files; confirm they are\nunclaimed before editing. Use the existing exam_corpus helpers where appropriate.\n\nImplement a read-only CLI accepting explicit inventory, manifest and receipt paths.\nCheck source identity, page/question references, question/answer pairing metadata,\nduplicate aliases, missing images, content/image hash mismatch and incompatible\nschema versions. Flag ambiguous numbering and unknown classifications. Emit an\nactionable report with IDs, reasons and source locations. Never repair/approve\nrecords, overwrite snapshots, load credentials, call providers or import Chroma.\n\nUse synthetic temporary files to test missing and conflicting answers, repeated\nquestion numbers across booklets, split solutions, stale receipts, path traversal,\nmissing images and a valid pair. Respect the distinction between structural validity\nand scientific correctness. Avoid rereading the whole corpus on every UI refresh.\n\nRun the specific tests through repository pytest so tests/conftest.py isolates data.\nUpdate your handoff with invocation examples, actual results and integration notes.\nSol reviews and wires this tool; do not modify its core modules.",
      "source": "FREEBUFF_PROMPTS.md / F1",
      "optional": false
    },
    {
      "id": "ST",
      "title": "Define versioned reasoning-tag records",
      "owner": "Sol",
      "phase": 1,
      "priority": "P0",
      "deps": [
        "S0"
      ],
      "summary": "Turn the new taxonomy draft into a small, testable annotation contract.",
      "deliverables": [
        "Tag registry and annotation schema",
        "Synthetic annotated example and validator"
      ],
      "acceptance": [
        "Knowledge, technique, representation, objective and misconception are separate",
        "Multiple routes and tag roles supported",
        "Version/aliases/proposed changes preserve old records"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK ST: Define versioned reasoning-tag records\n\nImplement the contract from docs/QUESTION_REASONING_TAXONOMY.md. Keep it a draft vocabulary pending human calibration. Include source/content revision, annotator identity/model, taxonomy version, primary/supporting/alternative/checking roles, short checkable evidence, unresolved labels and review state. Knowledge IDs must reference current book-backed catalogue nodes. Never treat technique presence as difficulty or a student's weakness. Provide a JSON schema or equivalent validator and synthetic fixtures for Freebuff. Preserve existing compatible question-design records; no bulk relabeling or promotion.",
      "source": "Roadmap-specific task",
      "optional": false
    },
    {
      "id": "H1",
      "title": "Confirm curriculum and seal evaluation sources",
      "owner": "You",
      "phase": 2,
      "priority": "P0",
      "deps": [
        "S1a",
        "F1"
      ],
      "summary": "Approve source identity and scope, then keep evaluation papers separate before tuning.",
      "deliverables": [
        "Current book/Maze scope revision",
        "Development and final-holdout source manifest"
      ],
      "acceptance": [
        "Duplicate originals in compilations are handled",
        "Final holdout remains outside authoring examples"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK H1: Confirm curriculum and seal evaluation sources\n\nConfirm the actual textbook editions and allowed lessons for each product mode, including the reviewed next Maze scope for weekly ranked matches. Teachers resolve disputed mappings. Historical exams provide design examples; they do not expand today's curriculum.\n\nAn initial planning proposal is approximately **300 source questions and 10–15 supported families**, spread across mathematics, physics and chemistry. These numbers are neither approved scope nor universal quality thresholds. Select coverage by concepts, figures, representations, difficulty mechanisms and recurring errors; document important omissions.\n\nBefore prompt improvement, freeze development and final evaluation manifests. Hold out whole exams and appropriate families. Detect the same questions appearing in compilations, answer PDFs, translated copies and near-duplicate variants; assign related material consistently. Keep final holdout questions, keys and review feedback out of authoring examples. If a final case informs development, retire it into development and replenish the holdout. Give the evaluator controlled access separately.\n\n**Handoff:** signed-off curriculum/scope revision, sample rationale, split manifest and duplicate exceptions.",
      "source": "HUMAN_TASKS.md / H1",
      "optional": false
    },
    {
      "id": "F2",
      "title": "Build the review interface",
      "owner": "Freebuff",
      "phase": 2,
      "priority": "P0",
      "deps": [
        "S0",
        "ST"
      ],
      "summary": "Make original images, transcriptions, tags and distinct review states easy to compare.",
      "deliverables": [
        "Standalone view and synthetic fixtures",
        "Mobile/RTL/keyboard screenshots and checks"
      ],
      "acceptance": [
        "Missing images and stale approvals are visible",
        "No raw HTML injection or blanket approval"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK F2: Build the review interface\n\nExecute F2 after the review contract is stable. Sol must assign a new standalone\nview/component and synthetic fixture/test files. The current local corpus viewer\nis Python-generated HTML in exam_quality_view.py, separate from React RagInspector;\ndo not assume they are one UI or edit their routing concurrently.\n\nBuild a review screen using the assigned contract and synthetic data first. Show\noriginal page/crop beside Persian transcription, ordered options, figure, answer\nsource, curriculum tags and separate evidence states. Include missing images,\ncontinuations, uncertain symbols, stale receipts, disagreement and zero eligible\nrecords. Clearly identify inferred labels and model-only judgments.\n\nSupport RTL, readable mathematics, keyboard navigation, zoom and narrow screens.\nEscape source/model text; never inject raw HTML or execute model content. Bind\nimage requests to approved source IDs rather than arbitrary file paths. Preserve\nthe existing visual style and accessibility. Do not add click animations or removed\nstreak/lifestyle/AI-customization panels.\n\nImplement human decision entry only against Sol's provided API/contract. A button\nmust not approve all records, impersonate an expert, or bypass hash/version checks.\nIf that API is absent, deliver a read-only preview with an explicit dependency.\n\nDeliver screenshots using synthetic data, actual checks, and a small integration\npatch proposal. Sol performs monitor/router wiring and authorization enforcement.",
      "source": "FREEBUFF_PROMPTS.md / F2",
      "optional": false
    },
    {
      "id": "S1b",
      "title": "Wire source-specific retrieval",
      "owner": "Sol",
      "phase": 3,
      "priority": "P0",
      "deps": [
        "H1",
        "S1a",
        "F1"
      ],
      "summary": "Route generation to eligible exam designs, facts to textbooks, and planning to Maze/test books.",
      "deliverables": [
        "Purpose-filtered retrieval",
        "Holdout/source-role leakage tests"
      ],
      "acceptance": [
        "Unknown/unreviewed sources cannot enter via fallback",
        "Old syllabus topics cannot expand current scope"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S1b: Wire source-specific retrieval\n\nSCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\nFinish review of F1, curriculum/split enforcement and role-specific retrieval. Source pairing already exists from S1a; extend it only for documented remaining defects.\n\nBROADER STAGE REFERENCE:\nExecute S1 using the S0 contracts and human H0-H1 source decisions. If any human\ndecision is absent, implement the schema and synthetic tests while holding the\naffected real source. Integrate Freebuff F1 only after reviewing its patch.\n\nExtend existing inventory/imports to link questions.pdf with answer-key.pdf and/or\nworked-solutions.pdf by confirmed exam/session/booklet identity and printed\nquestion number. Detect missing, repeated, conflicting and offset numbering,\nmulti-exam solution files, page continuations and ambiguous booklet variants.\nNever zip questions and answers by array position or filename alone.\n\nKeep source evidence, inferred design and scientific review independent. Preserve\noriginals and frozen snapshots; corrections produce versioned deltas. Bind answer\nand transcription receipts to their source and content hashes.\n\nImplement explicit retrieval purposes: authoring designs from eligible exam\nexamples; factual grounding from current textbooks; weekly plan scope from Maze\nplus test-book ranges and student data. Apply role, major, curriculum and split\nfilters before ranking. Unknown sources and unreviewed candidates cannot become\ntrusted evidence through a broad fallback. Old exam topics cannot expand scope.\n\nFreeze development and final-evaluation splits, including duplicate originals\ninside compilations and close question-family variants. Protect holdout answers\nfrom authoring prompts and blind solvers. Record retrieved IDs and filter reasons.\nTest cross-role leakage, stale reviews, ambiguous answer joins and missing scope.\nReturn measured coverage and unresolved source mappings; do not bulk approve data.",
      "source": "SOL_PROMPTS.md / S1",
      "optional": false
    },
    {
      "id": "SR",
      "title": "Integrate review records and safe decisions",
      "owner": "Sol",
      "phase": 4,
      "priority": "P0",
      "deps": [
        "S1b",
        "F2",
        "ST"
      ],
      "summary": "Wire the interface to hash-bound records so reviewers can work on real development packets.",
      "deliverables": [
        "Integrated local review workflow",
        "Version-bound decision storage and access tests"
      ],
      "acceptance": [
        "Decisions become stale after relevant edits",
        "Human/scientific/source states stay independent"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK SR: Integrate review records and safe decisions\n\nReview and integrate Freebuff F2 using the S0/ST contracts. Wire safe original-image lookups and version-bound decision writes. Keep access local or admin-protected as appropriate, preserve existing control-token rules, and never expose credentials or arbitrary paths. Supply separate blind-solve and answer-bearing packets. Test human review attribution, stale hashes, unauthorized writes and malformed records. Make the H2 reviewers able to inspect and record decisions without editing raw JSON manually.",
      "source": "Roadmap-specific task",
      "optional": false
    },
    {
      "id": "H2",
      "title": "Review the first source-question sample",
      "owner": "You",
      "phase": 5,
      "priority": "P0",
      "deps": [
        "SR",
        "H1"
      ],
      "summary": "Check source fidelity and scientific validity before treating records as authoring evidence.",
      "deliverables": [
        "Up to 50 reviewed development question records",
        "Corrections and unresolved items"
      ],
      "acceptance": [
        "Blind solving precedes answer revelation",
        "Critical symbols/options/figures checked against originals"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK H2: Review the first source-question sample\n\nReview the supplied anonymous item and original source regions, where relevant.\nRecord your reviewer ID, subject, date and exact item/version ID.\nIf doing both passes, perform the blind portion of Pass B before seeing any\nanswer-bearing source in Pass A. Request separate question and answer packets.\n\nPass A: compare the transcription with the image. Mark each field accurate,\nincorrect or unreadable; give page/region references and literal corrections.\nDo not reconstruct missing symbols from what you believe the question means.\n\nPass B: first solve without seeing the proposed answer, explanation or model\nverdict. Record a short checkable derivation. Then inspect all options and the\nkey. Check curriculum, domains, units, sufficient givens, unique answer and\nfigure consistency. Distinguish source mistakes from extraction mistakes.\n\nRubric: for each dimension mark pass / defect / uncertain / not applicable.\nDimensions: transcription; curriculum; scientific correctness; unique answer;\nwording; figure; distractors; cognitive demand; exam likeness; originality.\nExplain defects with a specific counterexample or correction. Describe the\nshortest solution and what reasoning is genuinely necessary. Do not equate\nlong arithmetic with difficulty or claim student-calibrated difficulty.\n\nFinish with accept for the stated purpose / hold for correction / unresolved.\nRecord what evidence would resolve uncertainty. Do not approve unseen items.",
      "source": "HUMAN_TASKS.md / H2",
      "optional": false
    },
    {
      "id": "HA",
      "title": "Collect independent model annotations",
      "owner": "You",
      "phase": 6,
      "priority": "P0",
      "deps": [
        "H2",
        "ST"
      ],
      "summary": "Give the same reviewed development packet separately to Claude and GPT Astra, if accessible.",
      "deliverables": [
        "Annotation A and B, separately attributed",
        "Model labels, source versions and explicit uncertainty"
      ],
      "acceptance": [
        "Neither annotator sees the other's answers",
        "No holdout questions or credentials in the packet",
        "No new paid service required"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK HA: Collect independent model annotations\n\nUse the independent annotation prompt in docs/QUESTION_REASONING_TAXONOMY.md with the same bounded development packet. Run it separately in Claude and GPT Astra using access you already have. Each must inspect the question, figures and checked solution, use stable tag IDs, justify roles with short evidence, and preserve uncertainty. Do not show one result to the other. If a model is unavailable, record that and use another available independent annotator or a human; do not buy access. Return both outputs with exact model/source/taxonomy versions for F4. These are candidate labels, not human-reviewed facts.",
      "source": "Roadmap-specific task",
      "optional": false
    },
    {
      "id": "F4",
      "title": "Compare labels and draft taxonomy changes",
      "owner": "Freebuff",
      "phase": 7,
      "priority": "P0",
      "deps": [
        "HA"
      ],
      "summary": "Compare independent annotations, retaining legitimate alternative solution routes.",
      "deliverables": [
        "Disagreement table with evidence",
        "Proposed additions/merges/deprecations"
      ],
      "acceptance": [
        "Agreements are also sampled for review",
        "No unilateral registry changes or automatic approval"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK F4: Compare labels and draft taxonomy changes\n\nSCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\nCompare the two HA annotation outputs using QUESTION_REASONING_TAXONOMY.md. Group differences into missing evidence, label ambiguity, real mathematical disagreement, and valid alternative routes. Propose registry changes with examples and migration impact. Do not generate new questions in this step or adjudicate human approval. Mark your conclusions as candidates.\n\nBROADER STAGE REFERENCE:\nExecute F4 only on the small development batch assigned by Sol, never final holdouts.\nUse existing authorized free tools within limits; do not launch unbounded API work.\n\nFor each eligible source question, propose curriculum-backed skills, necessary\ninsight, representation changes, shortest checkable solution, distractor mechanisms\nand what makes the item demanding. Cite exact source/question IDs and retain unknowns.\nFlag OCR uncertainty before interpreting a formula. Do not infer an author's private\nthoughts or invent a source solution. Distinguish your solution from the printed key.\n\nSuggest one practice variation and one substantively different reasoning design.\nExplain the difference beyond changed numbers. Save candidate annotations under\nignored backend/data/authoring_work/ using the contract, marked model-inferred and\nhuman_reviewed=false. Include model label, input revision and concise checkable\nevidence; do not store hidden reasoning or secrets.\n\nStop at the assigned batch size. Send disagreements and proposed designs to human\nH2-H3 and Sol. Your output is review material and cannot promote the question bank.",
      "source": "FREEBUFF_PROMPTS.md / F4",
      "optional": false
    },
    {
      "id": "HT",
      "title": "Adjudicate labels and approve taxonomy v1",
      "owner": "You",
      "phase": 8,
      "priority": "P0",
      "deps": [
        "F4"
      ],
      "summary": "Review disputed labels plus a sample of agreements with a subject expert.",
      "deliverables": [
        "Reviewed annotation sample",
        "Accepted/rejected taxonomy proposals"
      ],
      "acceptance": [
        "Definitions include inclusion/exclusion examples",
        "Alternative solutions are preserved",
        "Unknowns are held rather than forced into tags"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK HT: Adjudicate labels and approve taxonomy v1\n\nReview F4's comparison using the original questions and checked solutions. Resolve the meaning of the label, not which model won. Sample agreements for shared mistakes. Approve, reject or hold each proposed addition/merge/deprecation and record its reason. Confirm stable IDs and aliases with Sol before changing the registry. Return reviewed source-bound labels and a taxonomy version suitable for a small authoring pilot. Do not label more data until the main definition disagreements are resolved.",
      "source": "Roadmap-specific task",
      "optional": false
    },
    {
      "id": "F3",
      "title": "Prepare adversarial and recovery tests",
      "owner": "Freebuff",
      "phase": 6,
      "priority": "P0",
      "deps": [
        "ST",
        "H2"
      ],
      "summary": "Test the known failure classes while annotation and human review run independently.",
      "deliverables": [
        "Synthetic mathematical defect fixtures",
        "Provider/network/restart test cases"
      ],
      "acceptance": [
        "Fixture mathematics independently checked",
        "No real VPN disruption or quota resets"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK F3: Prepare adversarial and recovery tests\n\nExecute F3 in a new Sol-assigned test module. Inspect existing suites first and\ncover missing behavior, not duplicated assertions or implementation details.\n\nConstruct minimal synthetic cases for contradictory quadrant/domain constraints,\nequivalent options, incorrect option reordering, wrong answer-PDF joins, graph/text\ndisagreement, obsolete curriculum tags and copied question structures. Include a\ncorrect but too-easy question and a valid difficult one with explicit expected\nevidence. Have Sol or a human check mathematical fixture truth before relying on it.\n\nTest that stale source hashes invalidate approvals, interrupted requests preserve\ncompleted stages, provider errors do not mark questions corrupt, terminal daily\nquotas are respected, independent keys remain independent, and duplicate worker\nclaims cannot publish twice. Use temporary storage and stubbed transports; never\ndisconnect the user's VPN or mutate real quota/checkpoint files.\n\nFor each failing case, return a minimal reproduction, expected behavior and actual\nbehavior. Fix only your assigned helper/fixture files. Report core defects to Sol\nwith file/function references. Do not relax assertions or eligibility to get green.",
      "source": "FREEBUFF_PROMPTS.md / F3",
      "optional": false
    },
    {
      "id": "S2",
      "title": "Build checked question constructors",
      "owner": "Sol",
      "phase": 9,
      "priority": "P0",
      "deps": [
        "HT",
        "S1b",
        "H2"
      ],
      "summary": "Construct valid mathematical specifications before writing Persian questions and options.",
      "deliverables": [
        "Small set of supported design families",
        "Parameter/solution/figure checks",
        "Unpublished generated examples"
      ],
      "acceptance": [
        "Contradictory and underdetermined cases held",
        "Practice variants distinguished from new reasoning designs"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S2: Build checked question constructors\n\nExecute S2 after eligible source records and representative human H2 reviews exist.\nBuild on question_design.py, exam_blueprint.py and current generation code.\nBegin with a small set of reviewed math families; expand after demonstrable success.\n\nStore assessed skills, necessary insight, representation, shortest valid solution,\nessential assumptions, plausible misconceptions, distractor mechanisms and design\nprovenance. Inferred labels remain inferred until reviewed. Retrieve diverse designs\nwithin the allowed curriculum rather than selecting only nearest wording.\n\nGenerate a structured problem specification before prose: domains, givens, units,\nunknown, constraints, constructed parameters, solution evidence and optional figure.\nCheck existence and answer uniqueness before writing ordered options and Persian\nwording. Use safe declarative specifications and allowlisted math operations; never\nexecute arbitrary model Python. Exact checks apply only to supported families;\nunsupported/inconclusive cases remain pending.\n\nProduce figures from the same specification as the mathematics. Validate labels,\nscales, topology and stated assumptions. Separate reusable practice variants from\nnew reasoning designs. Test whether a purported hard design collapses to direct\nsubstitution or an accidental shortcut. Extreme stays inside the current curriculum.\n\nPreserve existing textbook citations, independent verification and retry behavior.\nAdd reproducible tests for contradictory quadrants, extraneous roots, empty domains,\nequivalent options and figure/text disagreement. Save a small unpublished batch\nwith design/spec/source evidence for H3; do not claim creativity from prompt changes.",
      "source": "SOL_PROMPTS.md / S2",
      "optional": false
    },
    {
      "id": "S3",
      "title": "Enforce verification and resumable bank lifecycle",
      "owner": "Sol",
      "phase": 10,
      "priority": "P0",
      "deps": [
        "S2",
        "F3"
      ],
      "summary": "Make eligibility evidence-based and preserve every good question through worker failures.",
      "deliverables": [
        "Independent solve/audit and version invalidation",
        "Durable retry/claim behavior",
        "Question-level quarantine"
      ],
      "acceptance": [
        "Correctness and difficulty failures are separate",
        "Missing verification cannot publish",
        "Concurrent claims and restarts tested"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S3: Enforce verification and resumable bank lifecycle\n\nExecute S3. Extend existing question_quality, question_bank, pool and worker systems.\nIntegrate useful Freebuff F3 tests after independent review.\n\nSeparate a blind solve, exact supported checks, adversarial ambiguity/counterexample\nreview, and editorial/difficulty assessment. The blind solver must not receive the\ndraft answer or solution. Check final rendered wording and figures as well as the\nunderlying specification. Model agreement alone cannot create human review.\n\nKeep correctness, requested difficulty fit, novelty and human review distinct.\nA correct but basic item may be held for reclassification; a timeout is pending\nverification, not corrupt mathematics. Every substantive correction invalidates\naffected version-bound evidence. Preserve unaffected questions from failed booklets.\n\nImplement eligibility as a server-side policy derived from evidence. Reporting a\nquestion quarantines it according to the existing policy and stops future selection;\npreserve attempts and define how active sessions/ratings are handled. Do not silently\nrewrite an item already served to students.\n\nWorkers need durable stage checkpoints, idempotent completion, bounded retries,\nstale-lease recovery, graceful stop and distinct wait reasons. Preserve per-key/model\nquota state, actual retry deadlines and successful results. No assumption that keys\nshare capacity without evidence. Measure calls/tokens per accepted question using\navailable usage data; distinguish missing usage from zero.\n\nUse temporary databases and injected transport/provider failures to test restart,\nconcurrent claims, partial saves, access denial, daily quota, 503 and malformed data.\nReturn an eligibility matrix and specific failure evidence, not just a passing count.",
      "source": "SOL_PROMPTS.md / S3",
      "optional": false
    },
    {
      "id": "S4a",
      "title": "Prepare blinded development comparison",
      "owner": "Sol",
      "phase": 11,
      "priority": "P0",
      "deps": [
        "S3"
      ],
      "summary": "Compare topic-only, flat-tag and structured-design generation on equal development tasks.",
      "deliverables": [
        "Anonymous review packets",
        "Predeclared rubric and measured generation records"
      ],
      "acceptance": [
        "Same task mix and bounded budgets",
        "Generated/source identity hidden during initial review"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S4a: Prepare blinded development comparison\n\nSCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\nPrepare the development comparison and representative retrieval evaluation only. Include topic-only versus flat technique tags versus reasoning dependencies. Use development examples and do not open final holdouts. Give H3 anonymous packets with answer-free solving first. Product integration and final holdout evaluation happen later.\n\nBROADER STAGE REFERENCE:\nExecute S4 after S1-S3 and H3 reviews. Keep the final holdout sealed until the\npredeclared candidate is frozen. Tune on development only. Report all exclusions.\n\nCompare current generation with design-conditioned construction using the same\ncurriculum/task mix and bounded budgets. Include easy, Konkur, hard and extreme,\nfigures, and every subject claimed as supported. Measure correctness, ambiguity,\nunique answer, curriculum fidelity, originality, shortest-solution difficulty and\nteacher-rated exam likeness. Report numerator/denominator, disagreements and limits.\nEvaluate retrieval across subjects before changing dense/hybrid/reranker policy.\nNever select a production winner from the existing six-query pilot alone.\n\nIntegrate the reviewed bank into practice, full mocks and Colosseum. Preserve the\ncurrent full-paper count configuration, 10-question weekly Maze mode, and disclosed\nprevious-scope fallback. Insufficient coverage must not silently change the requested\nexam or serve unchecked items. Track version-level exposure and prefer items unseen\nby both ranked players. Hide answers/solutions until the appropriate server-side state.\n\nImplement clear loading, empty, retry and provider-wait states. Keep request latency\nindependent of background generation. Respect protected planner blocks, book test\nranges, homework synchronization and account isolation during integration.\n\nBefore Freebuff F5, supply an integrated isolated test harness with admin and\nnon-admin identities, review routes, representative pool fixtures and controlled\nprovider responses. The existing ui_fixture_server.py is a starting point; its\nordinary accounts and stubbed generation do not exercise all requested workflows.\nDeclare which routes/scenarios are implemented in the harness so missing fixtures\nare not mistaken for product defects. Never point it at the real student database.\n\nSupport H4 with first-attempt/exposure/assignment records, minimal participant IDs,\nand conservative difficulty estimates. No precise ability or discrimination claims\nfrom 20 users. Run targeted backend/frontend tests and actual local browser workflows.\nReturn a pilot report and remaining release blockers.",
      "source": "SOL_PROMPTS.md / S4",
      "optional": false
    },
    {
      "id": "H3",
      "title": "Judge quality and return specific corrections",
      "owner": "You",
      "phase": 12,
      "priority": "P0",
      "deps": [
        "S4a"
      ],
      "summary": "Use subject experts to assess correctness, useful difficulty, originality and exam likeness.",
      "deliverables": [
        "Blinded review results and disagreements",
        "Accepted question versions and corrections"
      ],
      "acceptance": [
        "Wrong answers cannot be hidden by average ratings",
        "Reviewed corrections feed development only"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK H3: Judge quality and return specific corrections\n\nHave Sol prepare randomized, anonymous packets with comparable subjects, scope, families and presentation. Hide generator identity, provider verdicts and generated-versus-source labels during initial judgment; reveal provenance afterward for source and novelty checks. Keep scoring rules fixed before reviewing results.\n\nRoutine H3 feedback uses development cases. Review final holdouts only after the candidate is frozen. If those results inform another improvement, move the affected cases into development and replace the final holdout before making a new evaluation claim.\n\nAsk teachers for actionable feedback: missing constraint, shortcut, misleading distractor, unsupported concept, copied structure or required insight. Preserve independent judgments before adjudicating disagreements. Report counts, denominators, unresolved items and critical defects alongside ratings. Strong average exam likeness cannot compensate for wrong answers. Feed back reviewed corrections, never unreviewed model accusations.",
      "source": "HUMAN_TASKS.md / H3",
      "optional": false
    },
    {
      "id": "S4b",
      "title": "Fix review findings and integrate student workflows",
      "owner": "Sol",
      "phase": 13,
      "priority": "P0",
      "deps": [
        "H3",
        "S3"
      ],
      "summary": "Close defects, then connect the qualified bank to practice, full mocks, Colosseum and planning.",
      "deliverables": [
        "Reviewed corrections and rerun evidence",
        "Integrated isolated admin/student QA harness",
        "Version/exposure and attempt records"
      ],
      "acceptance": [
        "Requested scope and shortages are honestly displayed",
        "Answers hidden until allowed",
        "Experimental items excluded from scored matches"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S4b: Fix review findings and integrate student workflows\n\nSCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\nResolve H3's blocking findings with regression checks, obtaining renewed review for changed items. Then finish product integration and supply Freebuff's isolated admin/non-admin test harness. Store first-attempt, exposure and assignment data. Keep tag hints hidden in assessments and optional in guided practice. Final holdout evaluation is S5a; real student pilot follows F5.\n\nBROADER STAGE REFERENCE:\nExecute S4 after S1-S3 and H3 reviews. Keep the final holdout sealed until the\npredeclared candidate is frozen. Tune on development only. Report all exclusions.\n\nCompare current generation with design-conditioned construction using the same\ncurriculum/task mix and bounded budgets. Include easy, Konkur, hard and extreme,\nfigures, and every subject claimed as supported. Measure correctness, ambiguity,\nunique answer, curriculum fidelity, originality, shortest-solution difficulty and\nteacher-rated exam likeness. Report numerator/denominator, disagreements and limits.\nEvaluate retrieval across subjects before changing dense/hybrid/reranker policy.\nNever select a production winner from the existing six-query pilot alone.\n\nIntegrate the reviewed bank into practice, full mocks and Colosseum. Preserve the\ncurrent full-paper count configuration, 10-question weekly Maze mode, and disclosed\nprevious-scope fallback. Insufficient coverage must not silently change the requested\nexam or serve unchecked items. Track version-level exposure and prefer items unseen\nby both ranked players. Hide answers/solutions until the appropriate server-side state.\n\nImplement clear loading, empty, retry and provider-wait states. Keep request latency\nindependent of background generation. Respect protected planner blocks, book test\nranges, homework synchronization and account isolation during integration.\n\nBefore Freebuff F5, supply an integrated isolated test harness with admin and\nnon-admin identities, review routes, representative pool fixtures and controlled\nprovider responses. The existing ui_fixture_server.py is a starting point; its\nordinary accounts and stubbed generation do not exercise all requested workflows.\nDeclare which routes/scenarios are implemented in the harness so missing fixtures\nare not mistaken for product defects. Never point it at the real student database.\n\nSupport H4 with first-attempt/exposure/assignment records, minimal participant IDs,\nand conservative difficulty estimates. No precise ability or discrimination claims\nfrom 20 users. Run targeted backend/frontend tests and actual local browser workflows.\nReturn a pilot report and remaining release blockers.",
      "source": "SOL_PROMPTS.md / S4",
      "optional": false
    },
    {
      "id": "F5",
      "title": "Run independent end-to-end QA",
      "owner": "Freebuff",
      "phase": 14,
      "priority": "P0",
      "deps": [
        "S4b"
      ],
      "summary": "Verify the integrated candidate using isolated accounts, realistic figures and failures.",
      "deliverables": [
        "Reproducible QA report",
        "Safe stop/resume runbook",
        "Mobile/RTL evidence"
      ],
      "acceptance": [
        "Auth/account isolation and admin checks pass",
        "No real student data modified",
        "Harness gaps distinguished from app bugs"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK F5: Run independent end-to-end QA\n\nExecute F5 against Sol's integrated local candidate and synthetic test accounts.\nUse the supplied fixture server/temporary database; never reuse a real student's\naccount for destructive testing. Do not access production without explicit scope.\nFirst verify S4 supplied admin/non-admin identities and the review/pool routes.\nThe older ui_fixture_server.py alone lacks some of these. Report missing harness\ncoverage as a dependency; do not switch to real services to complete the checklist.\n\nExercise login, separate-account planning, mock selection, shortage behavior,\nranked current/previous Maze scope, question images, answer hiding before submission,\nreport/quarantine, admin permissions and review workflow. Test small/mobile viewports\nand Persian formulas. Verify which frontend/backend revision is actually running.\n\nExercise safe worker stop/resume and injected network/provider failures using the\nexisting test harness. Show stored work survives and pending work resumes without\nduplicates or quota resets. A heartbeat alone does not prove page progress.\n\nWrite reproducible defects with steps, expected/actual results, sanitized evidence\nand severity. Update operator instructions only for commands you verified or label\nthem untested. Include how to open the monitor, identify active work, read wait\nreasons, stop safely and resume after reboot. Do not advertise 24/7 laptop operation\nwhile asleep or powered off.\n\nFinish with changed files, tests and their actual outputs, unresolved blockers and\nthe next reproducible action. Close only your finished owned terminals after checking\ntheir process descendants. Preserve active scanners, servers and user shells.",
      "source": "FREEBUFF_PROMPTS.md / F5",
      "optional": false
    },
    {
      "id": "SQ",
      "title": "Resolve QA blockers and prepare pilot build",
      "owner": "Sol",
      "phase": 15,
      "priority": "P0",
      "deps": [
        "F5"
      ],
      "summary": "Integrate fixes and verify the exact build the pilot will use.",
      "deliverables": [
        "QA defect dispositions",
        "Pilot revision and approved item manifest"
      ],
      "acceptance": [
        "Blocking QA issues fixed and retested",
        "Changed questions have renewed evidence"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK SQ: Resolve QA blockers and prepare pilot build\n\nResolve F5 findings and retest the affected workflows. Do not mark defects fixed from an explanation alone. Produce the exact local pilot revision and eligible question/version manifest, participant instructions and defect-reporting path. Keep experimental pilot outcomes separate from public ranking. Ask the human to run H4 only when this candidate passes its required checks; missing resources must be explicit.",
      "source": "Roadmap-specific task",
      "optional": false
    },
    {
      "id": "H4",
      "title": "Run a controlled student pilot",
      "owner": "You",
      "phase": 16,
      "priority": "P0",
      "deps": [
        "SQ",
        "H3"
      ],
      "summary": "Try the cleared questions with approximately 20 voluntary students and record actual problems.",
      "deliverables": [
        "Pseudonymous first-attempt/exposure feedback",
        "Defects, timings and uncertainty"
      ],
      "acceptance": [
        "No precise psychometric claims from a small pilot",
        "Experimental results do not change public ranked scores"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK H4: Run a controlled student pilot\n\nAfter teacher-cleared materials and Sol's readiness report, a proposed 20-student pilot can test comprehension, usability and obvious defects. It is not precise difficulty calibration, discrimination estimation or statistical proof of fairness.\n\nUse minimal pseudonymous IDs, voluntary participation and age-appropriate consent. Keep identity mapping separate; avoid unnecessary names, school details and sensitive free text. Agree retention and access before collection. Record item version, response, elapsed time, interruptions and reported ambiguity. Report sample sizes and uncertainty, including missing responses. Keep experimental results separate from public ranked ratings.\n\nIf you want to contribute code, claim a bounded task from Sol's board: a synthetic fixture, a minimal reproduction of a student-visible bug, or an operator usability check. Use the same file ownership and handoff rules as Freebuff. Keep source/expert decisions explicit even when you also implement the tool that records them.",
      "source": "HUMAN_TASKS.md / H4",
      "optional": false
    },
    {
      "id": "S5a",
      "title": "Close pilot issues and freeze a release candidate",
      "owner": "Sol",
      "phase": 17,
      "priority": "P0",
      "deps": [
        "H4"
      ],
      "summary": "Evaluate the frozen candidate and package only eligible resources with a rollback plan.",
      "deliverables": [
        "Pilot fixes and final held-out evaluation",
        "Release manifest and backup/restore plan",
        "Capacity plan and known limits"
      ],
      "acceptance": [
        "No unresolved critical item defects",
        "Existing release gates and claimed subject coverage pass",
        "No holdout tuning disguised as final evaluation"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S5a: Close pilot issues and freeze a release candidate\n\nSCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\nLOCAL PREPARATION ONLY. Resolve pilot issues with renewed review where needed, freeze the candidate, run final held-out evaluation once under the declared protocol, and prepare the release package. If final findings drive changes, retire affected cases to development and obtain replacement holdouts. Prepare target capacity/rollback checks; do not access VM, push, upload or activate. H5 reviews this concrete candidate.\n\nBROADER STAGE REFERENCE:\nPrepare S5 after the scoped pilot is accepted. This prompt first authorizes LOCAL\nrelease preparation. The existing AGENTS.md corpus restriction requires the user's\nexplicit later instruction before push, VM access, transfer or activation.\n\nReview all intended changes and Freebuff contributions; preserve unrelated dirty\nwork. Run appropriate integrated backend tests, frontend tests, TypeScript/build,\ndependency checks and secret/artifact checks. Historical pass counts are not current\nresults. Test auth/account isolation, admin authorization, answer-key secrecy,\nreports/quarantine, duplicate claims, interrupted sessions, scope fallback and backups.\n\nBuild a versioned release manifest containing code revision, eligible corpus IDs,\ncontent/image checksums, embedding provider/model/dimensions, schema and prompt\nversions, evaluation reports, limitations and rollback instructions. Export only\neligible shared resources. Never replace the application account database with the\nlaptop database. Keep raw PDFs, credentials, local scanner state and rejected data\nout of Git and frontend bundles.\n\nPrepare a target-capacity test for the 2GB VM: memory, startup, concurrency, storage\nand latencies under the intended pilot load. Keep OCR/heavy background work local.\nDocument a verified reserve policy and honest behavior when stock/provider capacity\nruns out. Do not promise uptime from free-tier keys alone.\n\nPresent the exact candidate and remaining decisions for H5. After explicit deployment\nauthorization, fetch first, preserve remote work, use fast-forward only, back up SQLite\nthrough its backup API and Chroma with writers stopped, preserve JWT secrets/accounts/\nprivate uploads, install compatible dependencies, import verified shared data and\ndeploy the same revision. Never copy a laptop localhost proxy to the VM.\n\nVerify the public frontend revision, API and authenticated workflows, not health200\nalone. Exercise rollback if verification fails. Send no OTP to an unapproved recipient.\nRecord deployed revision, corpus version, checks and unresolved limitations.",
      "source": "SOL_PROMPTS.md / S5",
      "optional": false
    },
    {
      "id": "H5",
      "title": "Choose the exact release and authorize rollout",
      "owner": "You",
      "phase": 18,
      "priority": "P0",
      "deps": [
        "S5a"
      ],
      "summary": "Review the release evidence and explicitly decide whether this candidate may be deployed.",
      "deliverables": [
        "Decision naming code revision and corpus snapshot",
        "Known limits and rollback owner"
      ],
      "acceptance": [
        "Approval refers to this candidate, not a general plan",
        "Required scientific and operational gates satisfied"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK H5: Choose the exact release and authorize rollout\n\nStage / date / owner:\nInput document, item and content revision IDs:\nCode revision / corpus snapshot:\nEvidence files and page references:\nExtraction status / scientific status / human reviewer:\nDecision and allowed purpose:\nUnresolved defects / exclusions / uncertainty:\nNext owner and required evidence:\nRelease candidate / previous snapshot / rollback owner, if applicable:",
      "source": "HUMAN_TASKS.md / H5",
      "optional": false
    },
    {
      "id": "S5b",
      "title": "Deploy the approved revision safely",
      "owner": "Sol",
      "phase": 19,
      "priority": "P0",
      "deps": [
        "H5"
      ],
      "summary": "Perform the actual deployment only after explicit authorization for the exact candidate.",
      "deliverables": [
        "Backups and verified shared-data import",
        "Backend/frontend deployment revision",
        "Authenticated checks and rollback evidence"
      ],
      "acceptance": [
        "Accounts/private uploads/JWT secret preserved",
        "Public frontend and API match candidate",
        "Health200 alone is not sufficient"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S5b: Deploy the approved revision safely\n\nSCOPE FOR THIS ROADMAP STEP (takes precedence over the broader stage below):\nDEPLOYMENT STAGE: proceed only after the user's explicit H5 authorization naming the candidate. A roadmap checkbox alone is not deployment permission. Follow S5's backup, fast-forward, private-data preservation, compatible import and public verification steps. On failed verification, roll back or stop with a concrete recovery record.\n\nBROADER STAGE REFERENCE:\nPrepare S5 after the scoped pilot is accepted. This prompt first authorizes LOCAL\nrelease preparation. The existing AGENTS.md corpus restriction requires the user's\nexplicit later instruction before push, VM access, transfer or activation.\n\nReview all intended changes and Freebuff contributions; preserve unrelated dirty\nwork. Run appropriate integrated backend tests, frontend tests, TypeScript/build,\ndependency checks and secret/artifact checks. Historical pass counts are not current\nresults. Test auth/account isolation, admin authorization, answer-key secrecy,\nreports/quarantine, duplicate claims, interrupted sessions, scope fallback and backups.\n\nBuild a versioned release manifest containing code revision, eligible corpus IDs,\ncontent/image checksums, embedding provider/model/dimensions, schema and prompt\nversions, evaluation reports, limitations and rollback instructions. Export only\neligible shared resources. Never replace the application account database with the\nlaptop database. Keep raw PDFs, credentials, local scanner state and rejected data\nout of Git and frontend bundles.\n\nPrepare a target-capacity test for the 2GB VM: memory, startup, concurrency, storage\nand latencies under the intended pilot load. Keep OCR/heavy background work local.\nDocument a verified reserve policy and honest behavior when stock/provider capacity\nruns out. Do not promise uptime from free-tier keys alone.\n\nPresent the exact candidate and remaining decisions for H5. After explicit deployment\nauthorization, fetch first, preserve remote work, use fast-forward only, back up SQLite\nthrough its backup API and Chroma with writers stopped, preserve JWT secrets/accounts/\nprivate uploads, install compatible dependencies, import verified shared data and\ndeploy the same revision. Never copy a laptop localhost proxy to the VM.\n\nVerify the public frontend revision, API and authenticated workflows, not health200\nalone. Exercise rollback if verification fails. Send no OTP to an unapproved recipient.\nRecord deployed revision, corpus version, checks and unresolved limitations.",
      "source": "SOL_PROMPTS.md / S5",
      "optional": false
    },
    {
      "id": "F6",
      "title": "Verify the published user experience",
      "owner": "Freebuff",
      "phase": 20,
      "priority": "P0",
      "deps": [
        "S5b"
      ],
      "summary": "Check the approved public rollout against the release acceptance list.",
      "deliverables": [
        "Public release smoke-test report",
        "Any reproducible regression and ownership"
      ],
      "acceptance": [
        "Only approved test accounts/actions used",
        "Actual revision checked",
        "No unauthorized OTP messages or destructive tests"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK F6: Verify the published user experience\n\nAfter the explicitly authorized deployment, verify the public frontend revision and approved test-account workflows from F5. Use only the accounts/actions permitted in the rollout instructions. Check mobile display, figures, practice pool delivery, Maze scope disclosure and error handling. No destructive tests, production data cleanup or unapproved SMS. Report evidence of the deployed version and immediate regressions to Sol; do not fix production independently.",
      "source": "Roadmap-specific task",
      "optional": false
    },
    {
      "id": "H6",
      "title": "Accept rollout and prioritize the next learning cycle",
      "owner": "You",
      "phase": 21,
      "priority": "P0",
      "deps": [
        "F6"
      ],
      "summary": "Confirm the release outcome and choose the next supported topics and review batches.",
      "deliverables": [
        "Release acceptance or rollback decision",
        "Prioritized topic/quality backlog"
      ],
      "acceptance": [
        "Known limits communicated",
        "Reported defects routed to question-version review"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK H6: Accept rollout and prioritize the next learning cycle\n\nReview Sol's deployment evidence and Freebuff's public checks. Confirm whether the rollout is accepted or needs rollback/correction. Choose the next source topics/design families based on missing coverage and student feedback. Retain per-version defect history, privacy and reviewer evidence. Any recurring monitoring should be explicitly commissioned; this roadmap does not start an automation.",
      "source": "Roadmap-specific task",
      "optional": false
    },
    {
      "id": "S6",
      "title": "Improve skill diagnosis with real student evidence",
      "owner": "Sol",
      "phase": 22,
      "priority": "P1",
      "deps": [
        "H6"
      ],
      "summary": "Use repeated, exposure-aware observations to improve personalized practice selection.",
      "deliverables": [
        "Conservative skill estimates and uncertainty",
        "Transfer-practice comparison"
      ],
      "acceptance": [
        "One wrong answer does not fail every tag",
        "Alternative correct routes respected",
        "Accuracy/retry/assignment effects distinguished"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S6: Improve skill diagnosis with real student evidence\n\nUse the new taxonomy and pilot/release attempt records to improve practice selection. Start with transparent aggregation and uncertainty rather than precise ability claims. Distinguish first attempts, hints, repeats, missing answers and different assignment policies. Validate suspected misconceptions with targeted follow-up tasks. Compare later performance on unfamiliar questions, not just repeated items. Preserve ranked fairness and obtain sufficient human/student evidence before advancing to calibrated models.",
      "source": "Roadmap-specific task",
      "optional": true
    },
    {
      "id": "S7",
      "title": "Evaluate whether fine-tuning adds value",
      "owner": "Sol",
      "phase": 22,
      "priority": "P2",
      "deps": [
        "H6"
      ],
      "summary": "Consider training only after a reviewed design dataset and a strong retrieval baseline exist.",
      "deliverables": [
        "Reviewed dataset feasibility report",
        "Held-out comparison plan and free-resource feasibility"
      ],
      "acceptance": [
        "No raw/unreviewed OCR used as trusted training targets",
        "No billing or compute purchase",
        "No training without adequate resources and explicit scope"
      ],
      "prompt": "Work in C:\\Users\\Arsam\\Desktop\\Boom-merged.\nRead AGENTS.md, docs/production-work-pack/README.md and\ndocs/QUESTION_REASONING_TAXONOMY.md. Follow the task's declared ownership.\nWork locally with existing free resources; preserve other agents' files,\noriginals, completed checkpoints, frozen snapshots and credential quota state.\nKeep secrets and private corpus data out of prompts/reports/Git. Do not infer\nhuman review or scientific correctness from model agreement. This task does\nnot authorize deployment. Deliver changed files, actual checks, evidence,\nremaining limitations and the next handoff. Complete only this step now.\n\nTASK S7: Evaluate whether fine-tuning adds value\n\nAssess whether enough reviewed curriculum/design-to-question examples and expert corrections exist for fine-tuning. Compare with the strongest tested retrieval/prompting baseline first. Preserve whole-paper and family holdouts. Propose annotation, generation and correction tasks with versioned evidence. Check actual accessible model/license/hardware constraints and the user's free-only budget. Produce a go/no-go recommendation; this step does not enable billing, rent compute, upload private corpora or start training.",
      "source": "Roadmap-specific task",
      "optional": true
    }
  ],
  "links": {
    "taxonomy": "../QUESTION_REASONING_TAXONOMY.md",
    "guide": "README.md"
  }
};
