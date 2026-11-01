# Freebuff F1 handoff — offline source/review input validator

**Date:** 23 October 2026
**Owner:** Freebuff
**Task:** F1 — offline source/review input validator (CONTRACTS.md v0.1)
**Status:** implementation complete and locally verified; **not accepted** pending Sol review.
F1 remains unchecked on the task board; only Sol edits the board and shared contracts.

This handoff supersedes the F0/F1 entries previously in this file. Task-board
history remains the record of F0 acceptance and the Phase 1 / 22–23 October
audits. The obsolete "CONTRACTS.md is missing" claims and the provisional file
names are removed below.

---

## 1. Delivered files (actual paths)

| Path | Purpose |
| --- | --- |
| `backend/scripts/validate_exam_review_inputs.py` | Read-only CLI. Stdlib only; does not import application modules, open the DB, scan PDFs or call providers. |
| `tests/exam_review_inputs_test.py` | 48 focused tests: synthetic temp JSON through the CLI, direct function probes of region/bbox/index checks, and a guard that the contract fixtures parse as JSON. |
| `tests/fixtures/authoring_source_contract/valid_contract_v0.1.json` | Illustrative structurally valid envelope with internally consistent content/image hashes and held eligibility. |
| `tests/fixtures/authoring_source_contract/invalid_contract_bad_sha.json` | Illustrative negative envelope (malformed hashes). |

**Path note:** the task board's writable-path column proposes
`backend/scripts/authoring_source_validator.py` and
`tests/authoring_source_validator_test.py`. The implementation already existed at
the paths above and the Phase 1 audit instructed Freebuff to correct them at its
existing owned paths rather than rename. Any rename needs Sol's confirmation; no
shared file or core module was touched.

---

## 2. Invocation

```bash
python backend/scripts/validate_exam_review_inputs.py \
  --inventory <inventory.json> \
  --manifest <manifest.json> \
  --output <validation-report.json> \
  [--base-dir <approved/root>] \
  [--strict]
```

Exit codes:

- `0` — no structural/schema errors (evidence holds may remain).
- `1` — structural/schema errors present; also used by `--strict` when holds exist.

Report fields: `structural_error_count`, `hold_count`, `total_violations`,
`by_type`, `by_reason_summary`, `structural_errors[]`, `holds[]`, `violations[]`
(union, each entry has `kind` = `structural`/`hold`, `type`, `id`, `reason`,
`location`). The report is always written when the output path is writable, even
for malformed inputs.

---

## 3. Checks implemented

**Schema / identity**
- Required fields per record type; `schema_version` must be `0.1`.
- `document_id`, `role`, `classification`, `classification_state`, positive
  revisions, aliases are lists of strings.
- Document `source_sha256`: lowercase 64-char SHA256, or null (held as unknown).

**Page and bounding box**
- `pdf_page` must be a real integer `>= 1` (one-based); `printed_page` null or
  `>= 1`.
- `bbox` must be four numbers, each in `[0, 1]`, strictly ordered
  `left < right` and `top < bottom`. Degenerate and inverted boxes are flagged.
- The same page rules apply to answer-provenance regions.

**Answer bounds**
- `normalized_answer_index` must be a real integer `0..3` at provenance and region
  level. Strings, floats, bools and null are rejected; there is no `int()`
  coercion.

**Cross-record receipt binding (the previously missing check)**
- `question_id_revision` must end in a one-based revision and resolve to a
  question sidecar in the same manifest.
- `content_hash` must equal that question's `literal_content_sha256`.
- `exact_image_figure_hashes` must equal the union of the question's
  `source_image_sha256` and `figure_sha256`.
- Unbound revisions, content mismatches, image/figure mismatches and
  unverifiable (null) target hashes are **holds** (`stale_evidence` /
  `unverifiable_evidence`), consistent with "stale evidence stays inspectable but
  cannot approve a current revision".

**Pairing**
- Mapping entries use one-based printed numbers; malformed entries are structural.
- Duplicate printed numbers in one mapping are held (`ambiguous_mapping`);
  repeated printed numbers across sidecars are held (`ambiguous_numbering`).
- Pairing session/booklet must agree with the referenced question document;
  unresolved states, null references and mappings with no matching sidecar are
  held. Never inferred from filenames or page offsets.

**Receipts**
- Required fields, outcome enum, ISO-8601 timestamp, SHA shape, list fields and
  `supersedes` shape.

**Malformed input**
- Missing/unreadable files, invalid JSON, non-list top-level documents and
  non-object entries are reported as structural findings. One bad entry does not
  stop validation of the remaining records. Partitioning guards types before
  attribute access.

**File-reference containment**
- Optional `--base-dir` approved root. Absolute paths, drive-letter paths, UNC
  paths, `..` traversal, NUL bytes and home shortcuts are rejected; containment
  and existence are checked against the base directory.
- Applies recursively to path-bearing keys (`source_file`, `*_path`, `*_paths`,
  `*_file`, `*_files`, `evidence_refs`), including nested region metadata.

Holds are never approvals: unknown/unresolved classification, unresolved pairing
or answer provenance, ambiguous numbering/mapping and stale evidence all remain
non-approving.

---

## 4. Verification (actual results)

Environment: project venv (the system Python 3.14 does not have project
dependencies, so full-suite runs must use the venv interpreter).

```bash
cd backend
./.venv/Scripts/python.exe -m pytest ../tests/exam_review_inputs_test.py -q --no-header -p no:cacheprovider
# 48 passed in 6.27s (latest local run)

./.venv/Scripts/python.exe -X utf8 -m pytest ../tests -q --no-header -p no:cacheprovider
# 1078 passed, 3 skipped in 97.02s
```

`tests/conftest.py` DB isolation and provider stubs were preserved; no application
import or DB access was added by F1.

**Audit probe (previously accepted silently), now rejected — CLI exit 1:**

```text
region 0 pdf_page must be a one-based integer (>= 1): 0            invalid_page_number (structural)
region 0 bbox is not normalized to [0,1]: [2, 2, -1, -1]           invalid_bbox (structural)
region 0 bbox is not ordered [left<right, top<bottom]: [2,2,-1,-1] invalid_bbox (structural)
answer_provenance is null; the answer source and bounds remain held answer_provenance_missing (hold)
content_hash does not match question 'probe:q1' (receipt eee... != content bbb...) stale_evidence (hold)
```

The report also records `structural_error_count=3` and `hold_count=2`; stderr
says structural errors exit with code 1.

**Encoding:** the CLI console output is ASCII-only and tests run subprocesses with
explicit UTF-8 decoding; the earlier `UnicodeDecodeError` reader-thread warning is
gone.

**Fixtures:** both JSON fixtures parse; the valid envelope's receipt
`content_hash` now equals the question's `literal_content_sha256`, and its
`exact_image_figure_hashes` equals the union of the image/figure hashes. They are
illustrative envelopes, not CLI inventory/manifest inputs.

---

## 5. Known limitations / unresolved contract questions

1. **Continuation references and option order** from the F1 instruction are not
   enforced because CONTRACTS v0.1 does not define those fields. Multi-region
   sidecars are preserved and every region is validated, but no explicit
   `continues_from` linkage is checked. Needs a contract decision before adding.
2. **Embedded instructions** in reference strings are not policed; references are
   checked structurally and for containment only. A text policy is needed first.
3. **No PDF text/image scanning.** Hashes are shape-checked, and `--base-dir`
   verifies reference existence/containment, but content is not re-hashed from
   files. Document records carry no file-path field in CONTRACTS v0.1.
4. **Receipt binding scope.** Binding covers revision + literal content hash +
   exact image/figure hash set; it does not bind individual evidence files.
5. **Reference-key detection is heuristic** (explicit names plus the suffixes
   above). Other naming conventions need contract clarification.
6. **Stale/unbound receipts are holds, not structural errors.** This follows the
   "stale evidence remains inspectable" rule; `--strict` gives hard failure if Sol
   prefers that for CI.
7. **Illustrative fixtures are envelopes,** not CLI inventory/manifest lists; CLI
   coverage lives in the test suite.

---

## 6. Proposed integration points for Sol

- Run the CLI as the preflight for authoring imports: block on
  `structural_error_count > 0`; treat holds as non-approval and surface their
  types/reasons to the review UI (F2).
- Map `hold` types into the eligibility-reason vocabulary; keep `stale_evidence`
  and `unverifiable_evidence` non-approving for the current revision.
- Decide whether receipt binding mismatches should become structural errors for
  integrations, or stay holds plus `--strict`.
- If S1a packet output drives the import, emit an inventory list (documents) and
  a manifest list (pairing/sidecar/receipts); `document_id` values must match.
- No wiring was done: nothing was imported into app startup, routers, DB,
  providers or scanners.

---

## 7. Next step

Sol reviews this handoff, the 48 tests and the CLI behavior above. F1 stays
unchecked until Sol accepts it. F2 remains blocked on that acceptance and on its
declared dependencies. No deployment, push, provider call or corpus activation was
performed.
