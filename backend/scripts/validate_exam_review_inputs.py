"""Read-only validator for exam authoring source/review inputs.

Checks source identity, page/question references, question/answer pairing
metadata, duplicate aliases, page and bounding-box shapes, revision/hash-bound
receipts, file-reference containment and schema compatibility. Emits a
machine-readable report; never repairs, approves, overwrites snapshots, loads
credentials, calls providers or imports application modules.

Exit codes:
  0  no structural/schema errors (evidence holds may still be present)
  1  structural/schema errors present, or evidence holds with ``--strict``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

SCHEMA_VERSION = "0.1"
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
WINDOWS_ABS_RE = re.compile(r"\A[A-Za-z]:")
PATH_SPLIT_RE = re.compile(r"[\\/]+")

STRUCTURAL = "structural"
HOLD = "hold"

ROLES = {"questions", "answers", "combined", "unknown"}
CLASSIFICATIONS = {"official_exam", "mock_exam", "textbook", "mock_plan", "unknown"}
CLASSIFICATION_STATES = {"inferred", "confirmed", "unresolved"}
OUTCOMES = {"passed", "failed", "unresolved"}

# Reference-bearing keys. Contract: references are local relative paths beneath
# the approved private root; absolute paths and parent-directory escapes are
# rejected. Any key ending in _path/_paths/_file/_files is treated the same way.
PATH_FIELD_NAMES = {
    "source_file",
    "file_path",
    "pdf_path",
    "render_path",
    "crop_path",
    "crop_paths",
    "image_paths",
    "figure_paths",
    "evidence_refs",
}
PATH_FIELD_SUFFIXES = ("_path", "_paths", "_file", "_files")

REQUIRED_DOC_FIELDS = {
    "schema_version",
    "document_id",
    "source_sha256",
    "role",
    "classification",
    "classification_state",
    "publisher",
    "year",
    "session",
    "major",
    "grade",
    "booklet_code",
    "exam_id",
    "revision",
    "aliases",
    "classification_evidence",
}

REQUIRED_PAIRING_FIELDS = {
    "pairing_id",
    "revision",
    "question_document_id",
    "answer_document_id",
    "exam_id",
    "session",
    "booklet_code",
    "mapping",
    "state",
}

REQUIRED_QUESTION_SIDECAR_FIELDS = {
    "question_id",
    "question_revision",
    "document_id",
    "printed_question_number",
    "section",
    "regions",
    "literal_content_sha256",
    "source_image_sha256",
    "figure_sha256",
    "answer_provenance",
    "issues",
}

REQUIRED_ANSWER_PROVENANCE_FIELDS = {
    "answer_document_id",
    "regions",
    "printed_question_number",
    "section",
    "booklet",
    "raw_key",
    "normalized_answer_index",
    "mapping_state",
    "pairing_revision",
}

REQUIRED_RECEIPT_FIELDS = {
    "receipt_id",
    "schema_version",
    "question_id_revision",
    "content_hash",
    "exact_image_figure_hashes",
    "curriculum_version",
    "reviewer_kind",
    "reviewer_identifier",
    "model_prompt_version",
    "timestamp",
    "dimension",
    "outcome",
    "evidence_refs",
    "issues",
    "supersedes",
}


# ---------------------------------------------------------------------------
# Violation helpers
# ---------------------------------------------------------------------------

def _violation(kind: str, vtype: str, record_id: str, reason: str,
               location: Any, id_key: Optional[str] = None) -> Dict[str, Any]:
    violation: Dict[str, Any] = {
        "kind": kind,
        "type": vtype,
        "id": record_id,
        "reason": reason,
        "location": str(location),
    }
    if id_key:
        violation[id_key] = record_id
    return violation


def _structural(vtype: str, record_id: str, reason: str, location: Any,
                id_key: Optional[str] = None) -> Dict[str, Any]:
    return _violation(STRUCTURAL, vtype, record_id, reason, location, id_key)


def _hold(vtype: str, record_id: str, reason: str, location: Any,
          id_key: Optional[str] = None) -> Dict[str, Any]:
    return _violation(HOLD, vtype, record_id, reason, location, id_key)


# ---------------------------------------------------------------------------
# Primitive type helpers
# ---------------------------------------------------------------------------

def _is_int(value: Any) -> bool:
    """True for real integers only (bools and strings are not integers)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _is_iso_timestamp(value: Any) -> bool:
    if not _is_nonempty_str(value):
        return False
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def _record_id(record: Dict[str, Any], key: str, fallback: Any) -> str:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return str(fallback)


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Tuple[Any, Optional[str]]:
    """Return (data, error_message). Never raises on malformed input."""
    if not path.exists():
        return None, "file not found"
    if not path.is_file():
        return None, "path is not a regular file"
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
    except UnicodeDecodeError as exc:
        return None, f"not valid UTF-8: {exc}"
    except OSError as exc:
        return None, f"unreadable: {exc}"


def _dict_records(records: List[Any], label: str, location: Path,
                  errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep JSON-object entries; report every malformed entry."""
    out: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(_structural(
                "malformed_record",
                f"{label}[{index}]",
                f"{label} entry {index} must be a JSON object, got {type(record).__name__}",
                location,
            ))
            continue
        out.append(record)
    return out


# ---------------------------------------------------------------------------
# File-reference containment
# ---------------------------------------------------------------------------

def _looks_like_path_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return key in PATH_FIELD_NAMES or key.endswith(PATH_FIELD_SUFFIXES)


def _iter_path_values(node: Any) -> Iterator[Tuple[str, str]]:
    """Yield (key, value) for path-bearing strings anywhere in a record."""
    if isinstance(node, dict):
        for key, value in node.items():
            if _looks_like_path_key(key):
                if isinstance(value, str):
                    yield key, value
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            yield key, item
            else:
                yield from _iter_path_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_path_values(item)


def _reference_problem(value: str, base_dir: Optional[Path]) -> Optional[Tuple[str, str]]:
    if "\x00" in value:
        return "path_invalid", "contains a NUL byte"
    if not value.strip():
        return "path_invalid", "is empty"
    if WINDOWS_ABS_RE.match(value) or value.startswith("/") or value.startswith("\\"):
        return "absolute_path", "is absolute; references must stay relative to the approved base directory"
    if value.startswith("~"):
        return "path_invalid", "uses a home-directory shortcut"
    parts = [part for part in PATH_SPLIT_RE.split(value) if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return "path_traversal", "contains a parent-directory segment"
    if base_dir is not None:
        candidate = base_dir / value
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            return "path_invalid", "could not be resolved"
        if resolved != base_dir and base_dir not in resolved.parents:
            return "path_escape", "resolves outside the approved base directory"
        if not candidate.exists():
            return "missing_reference", "does not exist beneath the approved base directory"
    return None


def check_references(record: Dict[str, Any], record_id: str, location: Any,
                     base_dir: Optional[Path]) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    for key, value in _iter_path_values(record):
        problem = _reference_problem(value, base_dir)
        if problem is None:
            continue
        vtype, detail = problem
        violations.append(_structural(
            vtype,
            record_id,
            f"{key} reference {value!r} {detail}",
            location,
        ))
    return violations


# ---------------------------------------------------------------------------
# Region / bbox / page checks
# ---------------------------------------------------------------------------

def check_bbox(bbox: Any, owner: str, index: int, location: Any,
               label: str = "region") -> List[Dict[str, Any]]:
    """Normalized, ordered [left, top, right, bottom] in [0, 1]."""
    if not (isinstance(bbox, list) and len(bbox) == 4):
        return [_structural(
            "invalid_bbox",
            owner,
            f"{label} {index} bbox must be a list of four numbers "
            f"[left, top, right, bottom]: {bbox!r}",
            location,
        )]
    if not all(_is_number(value) for value in bbox):
        return [_structural(
            "invalid_bbox",
            owner,
            f"{label} {index} bbox must contain only numbers: {bbox!r}",
            location,
        )]

    left, top, right, bottom = bbox
    violations: List[Dict[str, Any]] = []
    if not all(0.0 <= value <= 1.0 for value in bbox):
        violations.append(_structural(
            "invalid_bbox",
            owner,
            f"{label} {index} bbox is not normalized to [0,1]: {bbox!r}",
            location,
        ))
    if not (left < right and top < bottom):
        violations.append(_structural(
            "invalid_bbox",
            owner,
            f"{label} {index} bbox is not ordered [left<right, top<bottom]: {bbox!r}",
            location,
        ))
    return violations


def _check_page(value: Any, owner: str, location: Any,
                field: str, label: str) -> List[Dict[str, Any]]:
    if not _is_int(value) or value < 1:
        return [_structural(
            "invalid_page_number",
            owner,
            f"{label} {field} must be a one-based integer (>= 1): {value!r}",
            location,
        )]
    return []


def _check_region_list(regions: Any, owner: str, location: Any,
                       require_bbox: bool, label: str,
                       id_key: str) -> List[Dict[str, Any]]:
    if not isinstance(regions, list):
        return [_structural(
            "invalid_type",
            owner,
            f"{label}s must be a list, got {type(regions).__name__}",
            location,
            id_key,
        )]
    if not regions:
        return [_hold(
            "empty_regions",
            owner,
            f"{label}s is empty; page evidence is missing",
            location,
            id_key,
        )]

    violations: List[Dict[str, Any]] = []
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            violations.append(_structural(
                "malformed_record",
                owner,
                f"{label} {index} must be a JSON object, got {type(region).__name__}",
                location,
                id_key,
            ))
            continue

        if "pdf_page" not in region:
            violations.append(_structural(
                "missing_fields",
                owner,
                f"{label} {index} missing required field: pdf_page",
                location,
                id_key,
            ))
        else:
            violations.extend(_check_page(
                region.get("pdf_page"), owner, location, "pdf_page", f"{label} {index}",
            ))

        if "printed_page" in region:
            printed_page = region.get("printed_page")
            if printed_page is not None:
                violations.extend(_check_page(
                    printed_page, owner, location, "printed_page", f"{label} {index}",
                ))

        if require_bbox:
            if "bbox" not in region:
                violations.append(_structural(
                    "missing_fields",
                    owner,
                    f"{label} {index} missing required field: bbox",
                    location,
                    id_key,
                ))
            else:
                violations.extend(check_bbox(
                    region.get("bbox"), owner, index, location, label,
                ))
    return violations


# ---------------------------------------------------------------------------
# Hash fields
# ---------------------------------------------------------------------------

def _check_sha_field(record: Dict[str, Any], field: str, owner: str,
                     location: Any, id_key: str,
                     null_hold: str) -> List[Dict[str, Any]]:
    if field not in record:
        return []
    value = record.get(field)
    if value is None:
        return [_hold(null_hold, owner, f"{field} is null; binding is unknown", location, id_key)]
    if not _is_sha256(value):
        return [_structural(
            "malformed_sha256", owner, f"{field} is not a lowercase 64-character SHA256: {value!r}",
            location, id_key,
        )]
    return []


def _check_sha_list_field(record: Dict[str, Any], field: str, owner: str,
                          location: Any, id_key: str,
                          null_hold: str) -> List[Dict[str, Any]]:
    if field not in record:
        return []
    value = record.get(field)
    if value is None:
        return [_hold(null_hold, owner, f"{field} is null; binding is unknown", location, id_key)]
    if not isinstance(value, list):
        return [_structural(
            "invalid_type", owner, f"{field} must be a list, got {type(value).__name__}",
            location, id_key,
        )]
    malformed = [entry for entry in value if not _is_sha256(entry)]
    if malformed:
        return [_structural(
            "malformed_sha256", owner,
            f"{field} contains malformed hashes: {malformed[:3]!r}",
            location, id_key,
        )]
    return []


# ---------------------------------------------------------------------------
# Record checks
# ---------------------------------------------------------------------------

def check_document(doc: Dict[str, Any], location: Any) -> List[Dict[str, Any]]:
    owner = _record_id(doc, "document_id", Path(str(location)).name)
    id_key = "document_id"
    violations: List[Dict[str, Any]] = []

    missing = REQUIRED_DOC_FIELDS - set(doc)
    if missing:
        violations.append(_structural(
            "missing_fields", owner, f"missing required fields: {sorted(missing)}",
            location, id_key,
        ))

    if doc.get("schema_version") != SCHEMA_VERSION:
        violations.append(_structural(
            "schema_version", owner,
            f"unsupported schema_version: {doc.get('schema_version')!r} (expected {SCHEMA_VERSION!r})",
            location, id_key,
        ))

    if not _is_nonempty_str(doc.get("document_id")):
        violations.append(_structural(
            "invalid_type", owner, f"document_id must be a non-empty string: {doc.get('document_id')!r}",
            location, id_key,
        ))

    violations.extend(_check_sha_field(doc, "source_sha256", owner, location, id_key,
                                       null_hold="unknown_source_hash"))

    role = doc.get("role")
    if role not in ROLES:
        violations.append(_structural(
            "invalid_enum", owner, f"invalid role: {role!r}; allowed {sorted(ROLES)}",
            location, id_key,
        ))

    classification = doc.get("classification")
    if classification not in CLASSIFICATIONS:
        violations.append(_structural(
            "invalid_enum", owner,
            f"invalid classification: {classification!r}; allowed {sorted(CLASSIFICATIONS)}",
            location, id_key,
        ))

    state = doc.get("classification_state")
    if state not in CLASSIFICATION_STATES:
        violations.append(_structural(
            "invalid_enum", owner,
            f"invalid classification_state: {state!r}; allowed {sorted(CLASSIFICATION_STATES)}",
            location, id_key,
        ))

    revision = doc.get("revision")
    if not _is_int(revision) or revision < 1:
        violations.append(_structural(
            "invalid_revision", owner,
            f"revision must be a positive integer: {revision!r}",
            location, id_key,
        ))

    aliases = doc.get("aliases")
    if not isinstance(aliases, list):
        violations.append(_structural(
            "invalid_type", owner, f"aliases must be a list, got {type(aliases).__name__}",
            location, id_key,
        ))
    elif not all(isinstance(alias, str) for alias in aliases):
        violations.append(_structural(
            "invalid_type", owner, "aliases must contain only strings",
            location, id_key,
        ))

    evidence = doc.get("classification_evidence")
    if evidence is not None and not isinstance(evidence, str):
        violations.append(_structural(
            "invalid_type", owner,
            f"classification_evidence must be a string or null: {evidence!r}",
            location, id_key,
        ))

    return violations


def check_pairing(pairing: Dict[str, Any], location: Any,
                  docs_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
                  question_sidecars: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    docs_by_id = docs_by_id or {}
    question_sidecars = question_sidecars or []
    owner = _record_id(pairing, "pairing_id", Path(str(location)).name)
    id_key = "pairing_id"
    violations: List[Dict[str, Any]] = []

    missing = REQUIRED_PAIRING_FIELDS - set(pairing)
    if missing:
        violations.append(_structural(
            "missing_fields", owner, f"missing required fields: {sorted(missing)}",
            location, id_key,
        ))

    pairing_revision = pairing.get("revision")
    if not _is_int(pairing_revision) or pairing_revision < 1:
        violations.append(_structural(
            "invalid_revision", owner,
            f"revision must be a positive integer: {pairing_revision!r}",
            location, id_key,
        ))

    question_document_id = pairing.get("question_document_id")
    answer_document_id = pairing.get("answer_document_id")
    for field, doc_id in (("question_document_id", question_document_id),
                          ("answer_document_id", answer_document_id)):
        if doc_id is None:
            violations.append(_hold(
                "unresolved_pairing", owner,
                f"{field} is null; the pairing cannot be resolved",
                location, id_key,
            ))
        elif not _is_nonempty_str(doc_id):
            violations.append(_structural(
                "invalid_type", owner,
                f"{field} must be a non-empty string or null: {doc_id!r}",
                location, id_key,
            ))
        elif docs_by_id and doc_id not in docs_by_id:
            violations.append(_hold(
                "unresolved_reference", owner,
                f"{field} {doc_id!r} is not present in the inventory",
                location, id_key,
            ))

    question_doc = docs_by_id.get(question_document_id) if isinstance(question_document_id, str) else None
    if question_doc:
        for field in ("session", "booklet_code"):
            declared = pairing.get(field)
            actual = question_doc.get(field)
            if declared is not None and actual is not None and declared != actual:
                violations.append(_hold(
                    "pairing_identity_mismatch", owner,
                    f"pairing {field} {declared!r} disagrees with question document {actual!r}",
                    location, id_key,
                ))

    state = pairing.get("state")
    if not _is_nonempty_str(state):
        violations.append(_structural(
            "invalid_type", owner, f"state must be a non-empty string: {state!r}",
            location, id_key,
        ))
    elif state in ("unresolved", "unknown", "candidate"):
        violations.append(_hold(
            "unresolved_pairing", owner,
            f"pairing state is {state!r}; the mapping remains held",
            location, id_key,
        ))

    mapping = pairing.get("mapping")
    if not isinstance(mapping, list):
        violations.append(_structural(
            "invalid_type", owner, f"mapping must be a list, got {type(mapping).__name__}",
            location, id_key,
        ))
        return violations
    if not mapping:
        violations.append(_hold(
            "unresolved_pairing", owner,
            "mapping is empty; no question/answer association is recorded",
            location, id_key,
        ))

    sidecars_by_key: Dict[Tuple[str, int], List[Any]] = {}
    for sidecar in question_sidecars:
        if not isinstance(sidecar, dict):
            continue
        doc_id = sidecar.get("document_id")
        number = sidecar.get("printed_question_number")
        if isinstance(doc_id, str) and _is_int(number):
            sidecars_by_key.setdefault((doc_id, number), []).append(sidecar.get("question_id"))

    seen_numbers: Dict[int, int] = {}
    for index, entry in enumerate(mapping):
        if not isinstance(entry, dict):
            violations.append(_structural(
                "malformed_record", owner,
                f"mapping entry {index} must be a JSON object, got {type(entry).__name__}",
                location, id_key,
            ))
            continue

        number = entry.get("printed_question_number")
        if not _is_int(number) or number < 1:
            violations.append(_structural(
                "invalid_numbering", owner,
                f"mapping entry {index} printed_question_number must be a one-based integer: {number!r}",
                location, id_key,
            ))
            continue

        previous = seen_numbers.get(number)
        if previous is not None:
            violations.append(_hold(
                "ambiguous_mapping", owner,
                f"printed question number {number} is mapped more than once "
                f"(entries {previous} and {index})",
                location, id_key,
            ))
        else:
            seen_numbers[number] = index

        for field in ("answer_document_id", "question_document_id"):
            if field in entry and not _is_nonempty_str(entry.get(field)):
                violations.append(_structural(
                    "invalid_type", owner,
                    f"mapping entry {index} {field} must be a non-empty string: {entry.get(field)!r}",
                    location, id_key,
                ))

        if isinstance(question_document_id, str) and sidecars_by_key:
            if not sidecars_by_key.get((question_document_id, number)):
                violations.append(_hold(
                    "unmatched_pair_mapping", owner,
                    f"mapping entry {index} (printed number {number}) has no question "
                    f"sidecar for document {question_document_id!r}",
                    location, id_key,
                ))

    return violations


def check_question_sidecar(sidecar: Dict[str, Any], location: Any,
                           docs_by_id: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    docs_by_id = docs_by_id or {}
    owner = _record_id(sidecar, "question_id", Path(str(location)).name)
    id_key = "question_id"
    violations: List[Dict[str, Any]] = []

    missing = REQUIRED_QUESTION_SIDECAR_FIELDS - set(sidecar)
    if missing:
        violations.append(_structural(
            "missing_fields", owner, f"missing required fields: {sorted(missing)}",
            location, id_key,
        ))

    if not _is_nonempty_str(sidecar.get("question_id")):
        violations.append(_structural(
            "invalid_type", owner, f"question_id must be a non-empty string: {sidecar.get('question_id')!r}",
            location, id_key,
        ))

    revision = sidecar.get("question_revision")
    if not _is_int(revision) or revision < 1:
        violations.append(_structural(
            "invalid_revision", owner,
            f"question_revision must be a positive integer: {revision!r}",
            location, id_key,
        ))

    document_id = sidecar.get("document_id")
    if not _is_nonempty_str(document_id):
        violations.append(_structural(
            "invalid_type", owner, f"document_id must be a non-empty string: {document_id!r}",
            location, id_key,
        ))
    elif docs_by_id and document_id not in docs_by_id:
        violations.append(_hold(
            "unresolved_reference", owner,
            f"document_id {document_id!r} is not present in the inventory",
            location, id_key,
        ))

    number = sidecar.get("printed_question_number")
    if not _is_int(number) or number < 1:
        violations.append(_structural(
            "invalid_numbering", owner,
            f"printed_question_number must be a one-based integer: {number!r}",
            location, id_key,
        ))

    if not _is_nonempty_str(sidecar.get("section")):
        violations.append(_structural(
            "invalid_type", owner, f"section must be a non-empty string: {sidecar.get('section')!r}",
            location, id_key,
        ))

    violations.extend(_check_region_list(
        sidecar.get("regions"), owner, location,
        require_bbox=True, label="region", id_key=id_key,
    ))

    violations.extend(_check_sha_field(
        sidecar, "literal_content_sha256", owner, location, id_key,
        null_hold="unknown_content_hash",
    ))
    violations.extend(_check_sha_list_field(
        sidecar, "source_image_sha256", owner, location, id_key,
        null_hold="unknown_image_hash",
    ))
    violations.extend(_check_sha_list_field(
        sidecar, "figure_sha256", owner, location, id_key,
        null_hold="unknown_figure_hash",
    ))

    if not isinstance(sidecar.get("issues"), list):
        violations.append(_structural(
            "invalid_type", owner, f"issues must be a list, got {type(sidecar.get('issues')).__name__}",
            location, id_key,
        ))

    violations.extend(check_answer_provenance(
        sidecar.get("answer_provenance"), location, owner_id=owner,
    ))

    return violations


def check_answer_provenance(provenance: Any, location: Any,
                            owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
    fallback_owner = Path(str(location)).name
    if owner_id is not None:
        owner = owner_id
    elif isinstance(provenance, dict):
        owner = _record_id(provenance, "question_id", fallback_owner)
    else:
        owner = fallback_owner
    id_key = "question_id"

    if provenance is None:
        return [_hold(
            "answer_provenance_missing", owner,
            "answer_provenance is null; the answer source and bounds remain held",
            location, id_key,
        )]
    if not isinstance(provenance, dict):
        return [_structural(
            "invalid_type", owner,
            f"answer_provenance must be a JSON object or null, got {type(provenance).__name__}",
            location, id_key,
        )]

    violations: List[Dict[str, Any]] = []
    missing = REQUIRED_ANSWER_PROVENANCE_FIELDS - set(provenance)
    if missing:
        violations.append(_structural(
            "missing_fields", owner, f"missing required fields: {sorted(missing)}",
            location, id_key,
        ))

    answer_document_id = provenance.get("answer_document_id")
    if answer_document_id is None:
        violations.append(_hold(
            "unresolved_answer_source", owner,
            "answer_document_id is null; the answer source remains held",
            location, id_key,
        ))
    elif not _is_nonempty_str(answer_document_id):
        violations.append(_structural(
            "invalid_type", owner,
            f"answer_document_id must be a non-empty string or null: {answer_document_id!r}",
            location, id_key,
        ))

    number = provenance.get("printed_question_number")
    if not _is_int(number) or number < 1:
        violations.append(_structural(
            "invalid_numbering", owner,
            f"printed_question_number must be a one-based integer: {number!r}",
            location, id_key,
        ))

    for field in ("section", "booklet", "mapping_state"):
        if not _is_nonempty_str(provenance.get(field)):
            violations.append(_structural(
                "invalid_type", owner,
                f"{field} must be a non-empty string: {provenance.get(field)!r}",
                location, id_key,
            ))

    raw_key = provenance.get("raw_key")
    if not _is_nonempty_str(raw_key):
        violations.append(_structural(
            "invalid_type", owner, f"raw_key must be a non-empty string: {raw_key!r}",
            location, id_key,
        ))

    if provenance.get("mapping_state") == "unresolved":
        violations.append(_hold(
            "unresolved_mapping", owner,
            "mapping_state is 'unresolved'; the answer mapping remains held",
            location, id_key,
        ))

    index = provenance.get("normalized_answer_index")
    if not _is_int(index):
        violations.append(_structural(
            "invalid_answer_index", owner,
            f"normalized_answer_index must be an integer 0..3, not "
            f"{type(index).__name__}: {index!r}",
            location, id_key,
        ))
    elif not 0 <= index <= 3:
        violations.append(_structural(
            "invalid_answer_index", owner,
            f"normalized_answer_index out of range 0..3: {index!r}",
            location, id_key,
        ))

    pairing_revision = provenance.get("pairing_revision")
    if not _is_int(pairing_revision) or pairing_revision < 1:
        violations.append(_structural(
            "invalid_revision", owner,
            f"pairing_revision must be a positive integer: {pairing_revision!r}",
            location, id_key,
        ))

    regions = provenance.get("regions")
    if not isinstance(regions, list):
        violations.append(_structural(
            "invalid_type", owner,
            f"regions must be a list, got {type(regions).__name__}",
            location, id_key,
        ))
    elif not regions:
        violations.append(_hold(
            "empty_regions", owner,
            "answer provenance regions is empty; the answer page is unknown",
            location, id_key,
        ))
    else:
        for index_number, region in enumerate(regions):
            if not isinstance(region, dict):
                violations.append(_structural(
                    "malformed_record", owner,
                    f"provenance region {index_number} must be a JSON object, "
                    f"got {type(region).__name__}",
                    location, id_key,
                ))
                continue
            if "pdf_page" in region:
                violations.extend(_check_page(
                    region.get("pdf_page"), owner, location,
                    "pdf_page", f"provenance region {index_number}",
                ))
            if "printed_question_number" in region:
                region_number = region.get("printed_question_number")
                if not _is_int(region_number) or region_number < 1:
                    violations.append(_structural(
                        "invalid_numbering", owner,
                        f"provenance region {index_number} printed_question_number "
                        f"must be a one-based integer: {region_number!r}",
                        location, id_key,
                    ))
            if "normalized_answer_index" in region:
                region_index = region.get("normalized_answer_index")
                if not _is_int(region_index):
                    violations.append(_structural(
                        "invalid_answer_index", owner,
                        f"provenance region {index_number} normalized_answer_index "
                        f"must be an integer 0..3: {region_index!r}",
                        location, id_key,
                    ))
                elif not 0 <= region_index <= 3:
                    violations.append(_structural(
                        "invalid_answer_index", owner,
                        f"provenance region {index_number} normalized_answer_index "
                        f"out of range 0..3: {region_index!r}",
                        location, id_key,
                    ))
            if "raw_key" in region and not _is_nonempty_str(region.get("raw_key")):
                violations.append(_structural(
                    "invalid_type", owner,
                    f"provenance region {index_number} raw_key must be a non-empty string: "
                    f"{region.get('raw_key')!r}",
                    location, id_key,
                ))

    return violations


def check_receipt(receipt: Dict[str, Any], location: Any,
                  questions_by_revision: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    questions_by_revision = questions_by_revision or {}
    owner = _record_id(receipt, "receipt_id", Path(str(location)).name)
    id_key = "receipt_id"
    violations: List[Dict[str, Any]] = []

    missing = REQUIRED_RECEIPT_FIELDS - set(receipt)
    if missing:
        violations.append(_structural(
            "missing_fields", owner, f"missing required fields: {sorted(missing)}",
            location, id_key,
        ))

    if receipt.get("schema_version") != SCHEMA_VERSION:
        violations.append(_structural(
            "schema_version", owner,
            f"unsupported schema_version: {receipt.get('schema_version')!r} "
            f"(expected {SCHEMA_VERSION!r})",
            location, id_key,
        ))

    outcome = receipt.get("outcome")
    if outcome not in OUTCOMES:
        violations.append(_structural(
            "invalid_enum", owner,
            f"invalid outcome: {outcome!r}; allowed {sorted(OUTCOMES)}",
            location, id_key,
        ))

    for field in ("curriculum_version", "reviewer_kind", "reviewer_identifier",
                  "model_prompt_version", "dimension"):
        if not _is_nonempty_str(receipt.get(field)):
            violations.append(_structural(
                "invalid_type", owner,
                f"{field} must be a non-empty string: {receipt.get(field)!r}",
                location, id_key,
            ))

    timestamp = receipt.get("timestamp")
    if not _is_iso_timestamp(timestamp):
        violations.append(_structural(
            "invalid_timestamp", owner,
            f"timestamp must be an ISO-8601 string: {timestamp!r}",
            location, id_key,
        ))

    if not _is_sha256(receipt.get("content_hash")):
        violations.append(_structural(
            "malformed_sha256", owner,
            f"content_hash is not a lowercase 64-character SHA256: "
            f"{receipt.get('content_hash')!r}",
            location, id_key,
        ))

    exact_hashes = receipt.get("exact_image_figure_hashes")
    if not isinstance(exact_hashes, list):
        violations.append(_structural(
            "invalid_type", owner,
            f"exact_image_figure_hashes must be a list, "
            f"got {type(exact_hashes).__name__}",
            location, id_key,
        ))
    else:
        malformed = [entry for entry in exact_hashes if not _is_sha256(entry)]
        if malformed:
            violations.append(_structural(
                "malformed_sha256", owner,
                f"exact_image_figure_hashes contains malformed hashes: {malformed[:3]!r}",
                location, id_key,
            ))

    for field in ("evidence_refs", "issues"):
        if not isinstance(receipt.get(field), list):
            violations.append(_structural(
                "invalid_type", owner,
                f"{field} must be a list, got {type(receipt.get(field)).__name__}",
                location, id_key,
            ))

    supersedes = receipt.get("supersedes")
    if supersedes is not None and not _is_nonempty_str(supersedes):
        violations.append(_structural(
            "invalid_type", owner,
            f"supersedes must be a receipt id string or null: {supersedes!r}",
            location, id_key,
        ))

    # ---- Cross-record binding: revision, content hash and exact image/figure hashes
    question_id_revision = receipt.get("question_id_revision")
    target: Optional[Dict[str, Any]] = None
    if not _is_nonempty_str(question_id_revision):
        violations.append(_structural(
            "invalid_type", owner,
            f"question_id_revision must be a non-empty '<question_id>:<revision>' "
            f"string: {question_id_revision!r}",
            location, id_key,
        ))
    else:
        tail = question_id_revision.rsplit(":", 1)[-1]
        if not tail.isdigit() or int(tail) < 1:
            violations.append(_structural(
                "invalid_reference", owner,
                f"question_id_revision {question_id_revision!r} does not end in a "
                f"one-based revision number",
                location, id_key,
            ))
        target = questions_by_revision.get(question_id_revision)
        if target is None:
            violations.append(_hold(
                "stale_evidence", owner,
                f"receipt targets question revision {question_id_revision!r}, which is "
                f"not present in this manifest; the evidence cannot approve a current revision",
                location, id_key,
            ))

    if target is not None:
        target_id = target.get("question_id")

        expected_content = target.get("literal_content_sha256")
        content_hash = receipt.get("content_hash")
        if expected_content is None:
            violations.append(_hold(
                "unverifiable_evidence", owner,
                f"question {target_id!r} has no literal_content_sha256; "
                f"the receipt content hash cannot be verified",
                location, id_key,
            ))
        elif _is_sha256(content_hash) and content_hash != expected_content:
            violations.append(_hold(
                "stale_evidence", owner,
                f"content_hash does not match question {target_id!r} "
                f"(receipt {content_hash[:12]}... != content {expected_content[:12]}...)",
                location, id_key,
            ))

        source_hashes = target.get("source_image_sha256")
        figure_hashes = target.get("figure_sha256")
        expected_images: Optional[set] = None
        if isinstance(source_hashes, list) and isinstance(figure_hashes, list):
            expected_images = set(source_hashes) | set(figure_hashes)
        if expected_images is None:
            violations.append(_hold(
                "unverifiable_evidence", owner,
                f"question {target_id!r} has unknown image/figure hashes; "
                f"the receipt exact hashes cannot be verified",
                location, id_key,
            ))
        elif isinstance(exact_hashes, list):
            received = {entry for entry in exact_hashes if isinstance(entry, str)}
            if received != expected_images:
                missing_hashes = sorted(expected_images - received)
                extra_hashes = sorted(received - expected_images)
                violations.append(_hold(
                    "stale_evidence", owner,
                    f"exact_image_figure_hashes does not match question {target_id!r} "
                    f"(missing {len(missing_hashes)}, extra {len(extra_hashes)})",
                    location, id_key,
                ))

    return violations


# ---------------------------------------------------------------------------
# Cross-record holds
# ---------------------------------------------------------------------------

def check_ambiguous_numbering(records: List[Dict[str, Any]], location: Any) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    numbers: Dict[int, List[str]] = {}
    for record in records:
        number = record.get("printed_question_number")
        if not _is_int(number):
            continue
        numbers.setdefault(number, []).append(str(record.get("question_id", "unknown")))
    for number, ids in sorted(numbers.items()):
        if len(ids) > 1:
            violations.append(_hold(
                "ambiguous_numbering", f"printed:{number}",
                f"printed question number {number} appears in multiple questions: {ids}",
                location,
            ))
    return violations


def check_unknown_classification(records: List[Dict[str, Any]], location: Any) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    for record in records:
        state = record.get("classification_state")
        role = record.get("role")
        classification = record.get("classification")
        if state == "unresolved" or role == "unknown" or classification == "unknown":
            violations.append(_hold(
                "unknown_classification",
                _record_id(record, "document_id", "unknown"),
                f"classification_state={state!r}, role={role!r}, "
                f"classification={classification!r}; record held",
                location,
                "document_id",
            ))
    return violations


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _split_by_kind(violations: List[Dict[str, Any]],
                   structural: List[Dict[str, Any]],
                   holds: List[Dict[str, Any]]) -> None:
    for violation in violations:
        if violation.get("kind") == HOLD:
            holds.append(violation)
        else:
            structural.append(violation)


def _write_report(path: Path, report: Dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        print(f"ERROR: could not write report to {path}: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate exam authoring inputs (documents, pairings, question "
            "sidecars, answer provenance and review receipts) without modifying them."
        )
    )
    parser.add_argument("--inventory", type=Path, required=True,
                        help="Inventory JSON file (list of document records).")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Manifest JSON file (list of pairing/question/receipt records).")
    parser.add_argument("--output", type=Path, default=Path("validation-report.json"),
                        help="Report path (default: validation-report.json).")
    parser.add_argument("--base-dir", type=Path, default=None,
                        help=("Approved local root for record file references. "
                              "References must stay relative and contained beneath it."))
    parser.add_argument("--strict", action="store_true",
                        help=("Exit non-zero when evidence holds are present. "
                              "Structural/schema errors always exit non-zero."))
    args = parser.parse_args(argv)

    structural_errors: List[Dict[str, Any]] = []
    holds: List[Dict[str, Any]] = []

    base_dir: Optional[Path] = None
    if args.base_dir is not None:
        try:
            base_dir = args.base_dir.resolve(strict=True)
        except (OSError, RuntimeError):
            base_dir = None
            structural_errors.append(_structural(
                "input_error", "base_dir",
                f"base directory not found or unreadable: {args.base_dir}",
                args.base_dir,
            ))
        else:
            if not base_dir.is_dir():
                structural_errors.append(_structural(
                    "input_error", "base_dir",
                    f"base directory is not a directory: {args.base_dir}",
                    args.base_dir,
                ))
                base_dir = None

    inventory_data, inventory_error = _read_json(args.inventory)
    if inventory_error is not None:
        structural_errors.append(_structural(
            "input_error", "inventory",
            f"inventory could not be read: {inventory_error}",
            args.inventory,
        ))
        inventory = None
    elif not isinstance(inventory_data, list):
        structural_errors.append(_structural(
            "invalid_input_shape", "inventory",
            f"inventory must be a JSON list, got {type(inventory_data).__name__}",
            args.inventory,
        ))
        inventory = None
    else:
        inventory = inventory_data

    manifest_data, manifest_error = _read_json(args.manifest)
    if manifest_error is not None:
        structural_errors.append(_structural(
            "input_error", "manifest",
            f"manifest could not be read: {manifest_error}",
            args.manifest,
        ))
        manifest = None
    elif not isinstance(manifest_data, list):
        structural_errors.append(_structural(
            "invalid_input_shape", "manifest",
            f"manifest must be a JSON list, got {type(manifest_data).__name__}",
            args.manifest,
        ))
        manifest = None
    else:
        manifest = manifest_data

    inventory_records = (
        _dict_records(inventory, "inventory", args.inventory, structural_errors)
        if inventory is not None else []
    )
    manifest_records = (
        _dict_records(manifest, "manifest", args.manifest, structural_errors)
        if manifest is not None else []
    )

    pairings = [
        record for record in manifest_records
        if record.get("role") == "pairing" or "pairing_id" in record
    ]
    question_sidecars = [
        record for record in manifest_records
        if record.get("role") == "question_sidecar"
        or ("question_id" in record and "regions" in record)
    ]
    receipts = [
        record for record in manifest_records
        if record.get("role") == "receipt" or "receipt_id" in record
    ]
    standalone_provenance = [
        record for record in manifest_records
        if record.get("role") == "answer_provenance"
    ]

    docs_by_id: Dict[str, Dict[str, Any]] = {}
    for document in inventory_records:
        document_id = document.get("document_id")
        if not (isinstance(document_id, str) and document_id.strip()):
            continue
        if document_id in docs_by_id:
            holds.append(_hold(
                "duplicate_document_id", document_id,
                f"document_id {document_id!r} appears in multiple inventory records",
                args.inventory, "document_id",
            ))
            continue
        docs_by_id[document_id] = document

    questions_by_revision: Dict[str, Dict[str, Any]] = {}
    for sidecar in question_sidecars:
        question_id = sidecar.get("question_id")
        revision = sidecar.get("question_revision")
        if not (isinstance(question_id, str) and question_id.strip()):
            continue
        if not (_is_int(revision) and revision >= 1):
            continue
        key = f"{question_id}:{revision}"
        if key in questions_by_revision:
            holds.append(_hold(
                "duplicate_question_revision", question_id,
                f"question revision {key!r} appears in multiple sidecars",
                args.manifest, "question_id",
            ))
            continue
        questions_by_revision[key] = sidecar

    # ---- Run record checks
    for document in inventory_records:
        owner = _record_id(document, "document_id", "document")
        _split_by_kind(check_document(document, args.inventory), structural_errors, holds)
        _split_by_kind(
            check_references(document, owner, args.inventory, base_dir),
            structural_errors, holds,
        )

    for pairing in pairings:
        owner = _record_id(pairing, "pairing_id", "pairing")
        _split_by_kind(
            check_pairing(pairing, args.manifest, docs_by_id, question_sidecars),
            structural_errors, holds,
        )
        _split_by_kind(
            check_references(pairing, owner, args.manifest, base_dir),
            structural_errors, holds,
        )

    for sidecar in question_sidecars:
        owner = _record_id(sidecar, "question_id", "question")
        _split_by_kind(
            check_question_sidecar(sidecar, args.manifest, docs_by_id),
            structural_errors, holds,
        )
        _split_by_kind(
            check_references(sidecar, owner, args.manifest, base_dir),
            structural_errors, holds,
        )

    for provenance in standalone_provenance:
        owner = _record_id(provenance, "question_id", "provenance")
        _split_by_kind(
            check_answer_provenance(provenance, args.manifest, owner_id=owner),
            structural_errors, holds,
        )
        _split_by_kind(
            check_references(provenance, owner, args.manifest, base_dir),
            structural_errors, holds,
        )

    for receipt in receipts:
        owner = _record_id(receipt, "receipt_id", "receipt")
        _split_by_kind(
            check_receipt(receipt, args.manifest, questions_by_revision),
            structural_errors, holds,
        )
        _split_by_kind(
            check_references(receipt, owner, args.manifest, base_dir),
            structural_errors, holds,
        )

    _split_by_kind(
        check_ambiguous_numbering(question_sidecars, args.manifest),
        structural_errors, holds,
    )
    _split_by_kind(
        check_unknown_classification(inventory_records, args.inventory),
        structural_errors, holds,
    )

    violations = structural_errors + holds

    by_type: Dict[str, int] = {}
    by_reason: Dict[str, int] = {}
    for violation in violations:
        vtype = str(violation.get("type", "unknown"))
        by_type[vtype] = by_type.get(vtype, 0) + 1
        reason = str(violation.get("reason", ""))
        by_reason[reason] = by_reason.get(reason, 0) + 1

    report = {
        "inventory_file": str(args.inventory),
        "manifest_file": str(args.manifest),
        "base_dir": str(args.base_dir) if args.base_dir is not None else None,
        "schema_version": SCHEMA_VERSION,
        "structural_error_count": len(structural_errors),
        "hold_count": len(holds),
        "total_violations": len(violations),
        "by_type": by_type,
        "by_reason_summary": dict(list(by_reason.items())[:20]),
        "structural_errors": structural_errors,
        "holds": holds,
        "violations": violations,
    }

    written = _write_report(args.output, report)

    print(
        f"Validation complete: {len(structural_errors)} structural error(s), "
        f"{len(holds)} hold(s) across {len(violations)} finding(s)."
    )
    print(f"Report written to: {args.output}")
    print(f"  by type: {by_type}")

    if structural_errors:
        print("STRUCTURAL ERRORS: fix schema/input findings; exiting with code 1.",
              file=sys.stderr)
        return 1
    if args.strict and holds:
        print("STRICT MODE: evidence holds present; exiting with code 1.",
              file=sys.stderr)
        return 1
    if not written:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
