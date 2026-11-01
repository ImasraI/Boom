"""Synthetic tests for backend/scripts/validate_exam_review_inputs.py.

F1 offline source/review input validator. Every case builds small temporary JSON
files (or calls the validator functions directly) and asserts on the report and
exit code. No real DB, providers, Chroma, credentials or application imports.
"""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
VALIDATOR_SCRIPT = PROJECT_ROOT / "backend" / "scripts" / "validate_exam_review_inputs.py"


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def run_validator(
    inventory_path: Path,
    manifest_path: Path,
    output_path: Path,
    strict: bool = False,
    base_dir: Path | None = None,
) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable, str(VALIDATOR_SCRIPT),
        "--inventory", str(inventory_path),
        "--manifest", str(manifest_path),
        "--output", str(output_path),
    ]
    if base_dir is not None:
        cmd += ["--base-dir", str(base_dir)]
    if strict:
        cmd.append("--strict")
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
    )


def load_report(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def of_type(report: Dict[str, Any], violation_type: str) -> List[Dict[str, Any]]:
    return [v for v in report.get("violations", []) if v.get("type") == violation_type]


def write_inputs(tmp: Path, inventory: Any, manifest: Any):
    inventory_path = tmp / "inventory.json"
    manifest_path = tmp / "manifest.json"
    output_path = tmp / "report.json"
    save_json(inventory_path, inventory)
    save_json(manifest_path, manifest)
    return inventory_path, manifest_path, output_path


@pytest.fixture(scope="module")
def validator():
    spec = importlib.util.spec_from_file_location("f1_validator", VALIDATOR_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------
# Valid records (all fields consistent and cross-bound)
# ------------------------------------------------------------------------------

VALID_QUESTION_DOC = {
    "schema_version": "0.1",
    "document_id": "test:doc-001",
    "source_sha256": "a" * 64,
    "role": "questions",
    "classification": "mock_exam",
    "classification_state": "confirmed",
    "publisher": "Test Pub",
    "year": 2024,
    "session": "spring",
    "major": "mathematics",
    "grade": "12",
    "booklet_code": "A",
    "exam_id": "test:exam-001",
    "revision": 1,
    "aliases": [],
    "classification_evidence": "printed numbering matches source",
}

VALID_ANSWER_DOC = {
    "schema_version": "0.1",
    "document_id": "test:doc-002",
    "source_sha256": "0" * 64,
    "role": "answers",
    "classification": "mock_exam",
    "classification_state": "confirmed",
    "publisher": "Test Pub",
    "year": 2024,
    "session": "spring",
    "major": "mathematics",
    "grade": "12",
    "booklet_code": "A",
    "exam_id": "test:exam-001",
    "revision": 1,
    "aliases": [],
    "classification_evidence": "answer key matching the question booklet",
}

VALID_PAIRING = {
    "pairing_id": "test:pair-001",
    "revision": 1,
    "question_document_id": "test:doc-001",
    "answer_document_id": "test:doc-002",
    "exam_id": "test:exam-001",
    "session": "spring",
    "booklet_code": "A",
    "mapping": [
        {"printed_question_number": 1, "answer_document_id": "test:doc-002"}
    ],
    "state": "linked_candidate",
}

VALID_QUESTION_SIDECAR = {
    "question_id": "test:q1",
    "question_revision": 1,
    "document_id": "test:doc-001",
    "printed_question_number": 1,
    "section": "math",
    "regions": [
        {"pdf_page": 2, "printed_page": None, "bbox": [0.1, 0.2, 0.9, 0.4]}
    ],
    "literal_content_sha256": "b" * 64,
    "source_image_sha256": ["c" * 64],
    "figure_sha256": ["d" * 64],
    "answer_provenance": {
        "answer_document_id": "test:doc-002",
        "booklet": "A",
        "printed_question_number": 1,
        "section": "math",
        "regions": [
            {
                "pdf_page": 2,
                "printed_question_number": 1,
                "section": "math",
                "raw_key": "42",
                "normalized_answer_index": 0,
                "mapping_revision": 1,
            }
        ],
        "raw_key": "42",
        "normalized_answer_index": 0,
        "mapping_state": "verified",
        "pairing_revision": 1,
    },
    "issues": [],
}

VALID_RECEIPT = {
    "receipt_id": "test:receipt-001",
    "schema_version": "0.1",
    "question_id_revision": "test:q1:1",
    "content_hash": "b" * 64,
    "exact_image_figure_hashes": ["c" * 64, "d" * 64],
    "curriculum_version": "12th-math-v1",
    "reviewer_kind": "human",
    "reviewer_identifier": "teacher-1",
    "model_prompt_version": "0.1",
    "timestamp": "2026-10-22T12:00:00Z",
    "dimension": "extraction",
    "outcome": "passed",
    "evidence_refs": [],
    "issues": [],
    "supersedes": None,
}

VALID_INVENTORY = [VALID_QUESTION_DOC, VALID_ANSWER_DOC]
VALID_MANIFEST = [VALID_PAIRING, VALID_QUESTION_SIDECAR, VALID_RECEIPT]


# Structurally valid but deliberately held: nulls and missing evidence.
HELD_DOC = {
    "schema_version": "0.1",
    "document_id": "synthetic:doc-held",
    "source_sha256": None,
    "role": "questions",
    "classification": "mock_exam",
    "classification_state": "inferred",
    "publisher": None,
    "year": None,
    "session": None,
    "major": None,
    "grade": None,
    "booklet_code": None,
    "exam_id": "synthetic:exam-held",
    "revision": 1,
    "aliases": [],
    "classification_evidence": None,
}

HELD_PAIRING = {
    "pairing_id": "synthetic:pair-held",
    "revision": 1,
    "question_document_id": "synthetic:doc-held",
    "answer_document_id": None,
    "exam_id": "synthetic:exam-held",
    "session": None,
    "booklet_code": None,
    "mapping": [{"printed_question_number": 1}],
    "state": "unresolved",
}

HELD_SIDECAR = {
    "question_id": "synthetic:q1",
    "question_revision": 1,
    "document_id": "synthetic:doc-held",
    "printed_question_number": 1,
    "section": "math",
    "regions": [
        {"pdf_page": 2, "printed_page": None, "bbox": [0.1, 0.2, 0.9, 0.4]}
    ],
    "literal_content_sha256": None,
    "source_image_sha256": [],
    "figure_sha256": [],
    "answer_provenance": None,
    "issues": [],
}


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


# ------------------------------------------------------------------------------
# Valid / held structural cases
# ------------------------------------------------------------------------------

def test_valid_records_pass(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    report = load_report(output_path)
    assert report["structural_error_count"] == 0, json.dumps(
        report["structural_errors"], ensure_ascii=False,
    )
    assert report["hold_count"] == 0, json.dumps(report["holds"], ensure_ascii=False)
    assert report["total_violations"] == 0
    # Cross-record receipt binding must actually be verified, not skipped.
    assert not of_type(report, "stale_evidence")


def test_valid_structural_but_held_example(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [HELD_DOC], [HELD_PAIRING, HELD_SIDECAR],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    report = load_report(output_path)
    assert report["structural_error_count"] == 0, json.dumps(
        report["structural_errors"], ensure_ascii=False,
    )
    assert report["hold_count"] >= 4
    held_types = {v["type"] for v in report["holds"]}
    assert {"unknown_source_hash", "unknown_content_hash",
            "answer_provenance_missing", "unresolved_pairing"} <= held_types


def test_strict_escalates_holds(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [HELD_DOC], [HELD_PAIRING, HELD_SIDECAR],
    )
    result = run_validator(inventory_path, manifest_path, output_path, strict=True)
    assert result.returncode == 1


def test_cli_output_is_ascii(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    result.stdout.encode("ascii")
    result.stderr.encode("ascii")


# ------------------------------------------------------------------------------
# Schema / structural failures
# ------------------------------------------------------------------------------

def test_missing_fields_is_structural(tmp_dir):
    bad_doc = {"schema_version": "0.1", "document_id": "test:doc-bad-missing"}
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [bad_doc], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    report = load_report(output_path)
    assert of_type(report, "missing_fields")
    assert report["structural_error_count"] > 0


def test_bad_sha256_is_structural(tmp_dir):
    bad_doc = copy.deepcopy(VALID_QUESTION_DOC)
    bad_doc["document_id"] = "test:doc-bad-sha"
    bad_doc["source_sha256"] = "not-a-valid-sha256-hash-that-is-too-short"
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [bad_doc], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    report = load_report(output_path)
    sha_violations = of_type(report, "malformed_sha256")
    assert any("source_sha256" in violation["reason"] for violation in sha_violations)


def test_pdf_page_zero_is_structural(tmp_dir):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["pdf_page"] = 0
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, sidecar, VALID_RECEIPT],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    report = load_report(output_path)
    page_violations = of_type(report, "invalid_page_number")
    assert page_violations
    assert any("pdf_page" in violation["reason"] for violation in page_violations)


def test_bbox_out_of_range_is_structural(tmp_dir):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["bbox"] = [2, 2, -1, -1]
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, sidecar, VALID_RECEIPT],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    bbox_violations = of_type(load_report(output_path), "invalid_bbox")
    assert any("normalized" in violation["reason"] for violation in bbox_violations)
    assert any("ordered" in violation["reason"] for violation in bbox_violations)


def test_bbox_unordered_is_structural(tmp_dir):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["bbox"] = [0.9, 0.1, 0.2, 0.4]
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, sidecar, VALID_RECEIPT],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    bbox_violations = of_type(load_report(output_path), "invalid_bbox")
    assert any("ordered" in violation["reason"] for violation in bbox_violations)


def test_bbox_wrong_shape_is_structural(tmp_dir):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["bbox"] = [0.1, 0.2, 0.9]
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, sidecar, VALID_RECEIPT],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    assert of_type(load_report(output_path), "invalid_bbox")


def test_answer_index_out_of_range_is_structural(tmp_dir):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["answer_provenance"]["normalized_answer_index"] = 5
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, sidecar],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    index_violations = of_type(load_report(output_path), "invalid_answer_index")
    assert index_violations


def test_answer_index_string_rejected_without_crash(tmp_dir):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["answer_provenance"]["normalized_answer_index"] = "1"
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, sidecar],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert "Traceback" not in result.stderr
    assert result.returncode == 1
    assert of_type(load_report(output_path), "invalid_answer_index")


# ------------------------------------------------------------------------------
# Direct function probes (the audit's exact complaint)
# ------------------------------------------------------------------------------

def _direct_sidecar_violations(validator, sidecar):
    return validator.check_question_sidecar(sidecar, Path("manifest.json"))


def test_direct_valid_sidecar_is_clean(validator):
    found = _direct_sidecar_violations(validator, copy.deepcopy(VALID_QUESTION_SIDECAR))
    assert found == [], json.dumps(found, ensure_ascii=False)


def test_direct_audit_probe_page_zero_and_inverted_bbox(validator):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["pdf_page"] = 0
    sidecar["regions"][0]["bbox"] = [2, 2, -1, -1]
    found = _direct_sidecar_violations(validator, sidecar)
    types = {violation["type"] for violation in found}
    assert "invalid_page_number" in types
    assert "invalid_bbox" in types


@pytest.mark.parametrize("bad_page", [0, -3, "2", 1.5, True, None])
def test_direct_page_must_be_one_based_integer(validator, bad_page):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["pdf_page"] = bad_page
    found = _direct_sidecar_violations(validator, sidecar)
    assert any(violation["type"] == "invalid_page_number" for violation in found)


@pytest.mark.parametrize(
    "bad_bbox",
    [
        [2, 2, -1, -1],
        [0.9, 0.1, 0.2, 0.4],
        [0.1, 0.2, 0.9],
        ["a", 0.2, 0.9, 0.4],
        None,
    ],
)
def test_direct_bbox_must_be_normalized_and_ordered(validator, bad_bbox):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["bbox"] = bad_bbox
    found = _direct_sidecar_violations(validator, sidecar)
    assert any(violation["type"] == "invalid_bbox" for violation in found)


def test_direct_answer_index_rejects_bool_and_float(validator):
    for bad_index in (True, 1.0, None):
        provenance = copy.deepcopy(VALID_QUESTION_SIDECAR["answer_provenance"])
        provenance["normalized_answer_index"] = bad_index
        found = validator.check_answer_provenance(provenance, Path("manifest.json"))
        assert any(violation["type"] == "invalid_answer_index" for violation in found), bad_index


# ------------------------------------------------------------------------------
# Cross-record receipt binding
# ------------------------------------------------------------------------------

def test_receipt_content_hash_mismatch_is_held(tmp_dir):
    receipt = copy.deepcopy(VALID_RECEIPT)
    receipt["content_hash"] = "e" * 64
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, VALID_QUESTION_SIDECAR, receipt],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0
    report = load_report(output_path)
    assert report["structural_error_count"] == 0
    stale = of_type(report, "stale_evidence")
    assert any("content_hash" in violation["reason"] for violation in stale)


def test_receipt_image_hash_mismatch_is_held(tmp_dir):
    receipt = copy.deepcopy(VALID_RECEIPT)
    receipt["exact_image_figure_hashes"] = ["c" * 64]
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, VALID_QUESTION_SIDECAR, receipt],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0
    stale = of_type(load_report(output_path), "stale_evidence")
    assert any("exact_image_figure_hashes" in violation["reason"] for violation in stale)


def test_receipt_unbound_revision_is_held(tmp_dir):
    receipt = copy.deepcopy(VALID_RECEIPT)
    receipt["question_id_revision"] = "test:q9:1"
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, VALID_QUESTION_SIDECAR, receipt],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0
    stale = of_type(load_report(output_path), "stale_evidence")
    assert any("test:q9:1" in violation["reason"] for violation in stale)


def test_receipt_without_any_sidecar_is_held(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_RECEIPT],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0
    report = load_report(output_path)
    assert report["structural_error_count"] == 0
    assert of_type(report, "stale_evidence")


def test_receipt_mismatch_fails_strict(tmp_dir):
    receipt = copy.deepcopy(VALID_RECEIPT)
    receipt["content_hash"] = "e" * 64
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, VALID_QUESTION_SIDECAR, receipt],
    )
    result = run_validator(inventory_path, manifest_path, output_path, strict=True)
    assert result.returncode == 1


# ------------------------------------------------------------------------------
# Holds that must not fail the default run
# ------------------------------------------------------------------------------

def test_duplicate_question_numbers_flagged(tmp_dir):
    sidecar_one = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar_one.update({"question_id": "test:q-dup1", "document_id": "test:doc-dup1"})
    sidecar_two = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar_two.update({"question_id": "test:q-dup2", "document_id": "test:doc-dup2"})
    doc_one = copy.deepcopy(VALID_QUESTION_DOC)
    doc_one["document_id"] = "test:doc-dup1"
    doc_two = copy.deepcopy(VALID_QUESTION_DOC)
    doc_two["document_id"] = "test:doc-dup2"
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [doc_one, doc_two], [sidecar_one, sidecar_two],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0
    numbering = of_type(load_report(output_path), "ambiguous_numbering")
    assert numbering


def test_unknown_classification_is_held(tmp_dir):
    unresolved_doc = copy.deepcopy(VALID_QUESTION_DOC)
    unresolved_doc["document_id"] = "test:doc-unresolved"
    unresolved_doc["classification_state"] = "unresolved"
    unknown_doc = copy.deepcopy(VALID_QUESTION_DOC)
    unknown_doc["document_id"] = "test:doc-unknown-role"
    unknown_doc["role"] = "unknown"
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [unresolved_doc, unknown_doc], [],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 0
    unknown = of_type(load_report(output_path), "unknown_classification")
    assert len(unknown) == 2


def test_legacy_path_traversal_does_not_crash(tmp_dir):
    bad_inventory = tmp_dir / "../../etc/passwd"
    manifest_path = tmp_dir / "manifest.json"
    output_path = tmp_dir / "report.json"
    save_json(manifest_path, [])
    result = run_validator(bad_inventory, manifest_path, output_path)
    assert result.returncode != -1
    assert output_path.exists()


# ------------------------------------------------------------------------------
# Malformed input handling
# ------------------------------------------------------------------------------

def test_manifest_not_a_list(tmp_dir):
    manifest_path = tmp_dir / "manifest.json"
    output_path = tmp_dir / "report.json"
    save_json(manifest_path, {"not": "a list"})
    inventory_path = tmp_dir / "inventory.json"
    save_json(inventory_path, VALID_INVENTORY)
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    report = load_report(output_path)
    assert of_type(report, "invalid_input_shape")


def test_manifest_entries_not_objects(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY,
        [1, "string-entry", None, VALID_QUESTION_SIDECAR, VALID_RECEIPT],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert "Traceback" not in result.stderr
    assert result.returncode == 1
    report = load_report(output_path)
    malformed = of_type(report, "malformed_record")
    assert len(malformed) == 3
    # Valid entries are still checked after malformed ones.
    assert report["structural_error_count"] >= 3


def test_manifest_invalid_json(tmp_dir):
    inventory_path = tmp_dir / "inventory.json"
    manifest_path = tmp_dir / "manifest.json"
    output_path = tmp_dir / "report.json"
    save_json(inventory_path, VALID_INVENTORY)
    manifest_path.write_text("{not valid json", encoding="utf-8")
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    report = load_report(output_path)
    assert of_type(report, "input_error")
    assert any("invalid JSON" in violation["reason"] for violation in report["violations"])


def test_inventory_entries_not_objects(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [1, VALID_QUESTION_DOC], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert "Traceback" not in result.stderr
    assert result.returncode == 1
    assert of_type(load_report(output_path), "malformed_record")


def test_missing_inventory_file(tmp_dir):
    inventory_path = tmp_dir / "does-not-exist.json"
    manifest_path = tmp_dir / "manifest.json"
    output_path = tmp_dir / "report.json"
    save_json(manifest_path, [])
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    report = load_report(output_path)
    assert any("inventory" in violation["reason"] for violation in of_type(report, "input_error"))


# ------------------------------------------------------------------------------
# File-reference containment
# ------------------------------------------------------------------------------

def _doc_with_reference(value: str) -> Dict[str, Any]:
    doc = copy.deepcopy(VALID_QUESTION_DOC)
    doc["source_file"] = value
    return doc


def test_reference_traversal_rejected(tmp_dir):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [_doc_with_reference("../../etc/passwd")], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    traversal = of_type(load_report(output_path), "path_traversal")
    assert traversal


@pytest.mark.parametrize("absolute", ["/etc/passwd", "C:\\secret.txt", "\\\\server\\share\\x.txt"])
def test_reference_absolute_rejected(tmp_dir, absolute):
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [_doc_with_reference(absolute)], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    assert of_type(load_report(output_path), "absolute_path")


def test_base_dir_accepts_contained_reference(tmp_dir):
    base = tmp_dir / "approved"
    base.mkdir()
    (base / "page-2.png").write_bytes(b"png")
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [_doc_with_reference("page-2.png"), VALID_ANSWER_DOC], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path, base_dir=base)
    assert result.returncode == 0, result.stderr
    report = load_report(output_path)
    assert report["total_violations"] == 0, json.dumps(report["violations"], ensure_ascii=False)


def test_base_dir_rejects_escape(tmp_dir):
    base = tmp_dir / "approved"
    base.mkdir()
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [_doc_with_reference("../outside.txt")], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path, base_dir=base)
    assert result.returncode == 1
    assert of_type(load_report(output_path), "path_traversal")


def test_base_dir_flags_missing_reference(tmp_dir):
    base = tmp_dir / "approved"
    base.mkdir()
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, [_doc_with_reference("missing.png")], VALID_MANIFEST,
    )
    result = run_validator(inventory_path, manifest_path, output_path, base_dir=base)
    assert result.returncode == 1
    assert of_type(load_report(output_path), "missing_reference")


def test_fixture_files_are_valid_json():
    fixture_dir = PROJECT_ROOT / "tests" / "fixtures" / "authoring_source_contract"
    fixtures = sorted(fixture_dir.glob("*.json"))
    assert fixtures, f"no fixtures found under {fixture_dir}"
    for fixture in fixtures:
        with fixture.open("r", encoding="utf-8") as handle:
            json.load(handle)


def test_nested_region_reference_rejected(tmp_dir):
    sidecar = copy.deepcopy(VALID_QUESTION_SIDECAR)
    sidecar["regions"][0]["render_path"] = "../escape.png"
    inventory_path, manifest_path, output_path = write_inputs(
        tmp_dir, VALID_INVENTORY, [VALID_PAIRING, sidecar, VALID_RECEIPT],
    )
    result = run_validator(inventory_path, manifest_path, output_path)
    assert result.returncode == 1
    assert of_type(load_report(output_path), "path_traversal")
