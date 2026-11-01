"""Local source sidecars: explicit identity joins, never OCR/scientific approval."""
from collections import defaultdict
from copy import deepcopy
import re
from app.rag.exam_corpus import payload_digest

IDENTITY = ("exam_id", "session", "booklet_code", "section", "printed_question_number")


def pairing_key(row):
    values = tuple(row.get(k) for k in IDENTITY)
    return values if all(v is not None and v != "" for v in values) else None


def pair_questions(questions, answers):
    """Join explicit printed identities. Repeated or ambiguous records stay held."""
    qgroups, agroups = defaultdict(list), defaultdict(list)
    for q in questions:
        qgroups[pairing_key(q)].append(q)
    for a in answers:
        agroups[pairing_key(a)].append(a)
    mappings = []
    for q in questions:
        key = pairing_key(q)
        candidates = agroups.get(key, []) if key else []
        issues = []
        if key is None:
            issues.append("incomplete_identity")
        elif len(qgroups[key]) != 1:
            issues.append("repeated_question_identity")
        if not candidates:
            issues.append("missing_answer")
        elif len(candidates) != 1:
            issues.append("ambiguous_or_conflicting_answers")
        a = candidates[0] if len(candidates) == 1 else None
        if a and (type(a.get("answer_index")) is not int or not 0 <= a["answer_index"] < 4):
            issues.append("missing_or_invalid_key")
        for item in (q, a):
            if item and (not re.fullmatch(r"[0-9a-f]{64}", str(item.get("content_sha256", ""))) or not isinstance(item.get("source_image_sha256"), list) or not item.get("source_image_sha256") or any(not re.fullmatch(r"[0-9a-f]{64}", str(h)) for h in item.get("source_image_sha256", []))):
                issues.append("missing_content_or_image_evidence")
            if item and item.get("continuation_state") not in (None, "not_needed", "reviewed"):
                issues.append("unresolved_continuation")
            if item and item.get("identity_state") != "confirmed":
                issues.append("identity_not_confirmed")
        mappings.append({"question_id": q["id"], "question_revision": q.get("revision"),
            "answer_id": a.get("id") if a else None,
            "question_content_sha256": q.get("content_sha256"),
            "answer_content_sha256": a.get("content_sha256") if a else None,
            "source_image_sha256": q.get("source_image_sha256"),
            "answer_image_sha256": a.get("source_image_sha256") if a else None,
            "author_answer_index": a.get("answer_index") if a else None,
            "state": "held" if issues else "linked_candidate",
            "issues": sorted(set(issues)), "scientific_state": "not_checked"})
    used = {m["answer_id"] for m in mappings if m["answer_id"]}
    return {"schema_version": "0.1", "mappings": mappings,
            "unmatched_answer_ids": [a["id"] for a in answers if a["id"] not in used],
            "eligible": False}


def receipt_matches(receipt, question, answer):
    """Association receipts bind both sides; a stale answer cannot reuse approval."""
    return (receipt.get("question_id") == question.get("id")
        and receipt.get("question_revision") == question.get("revision")
        and receipt.get("answer_id") == answer.get("id")
        and receipt.get("answer_revision") == answer.get("revision")
        and all(receipt.get(name) == value and bool(value) for name, value in (
            ("question_content_sha256", question.get("content_sha256")),
            ("answer_content_sha256", answer.get("content_sha256")),
            ("source_image_sha256", question.get("source_image_sha256")),
            ("answer_image_sha256", answer.get("source_image_sha256")))))


def packet_revision(documents, questions, answers, previous=None):
    """Append-only callers retain previous packets; never mutate frozen source data."""
    body = {"schema_version": "0.1", "documents": deepcopy(documents),
            "questions": deepcopy(questions), "answers": deepcopy(answers),
            "pairing": pair_questions(questions, answers),
            "split": {"state": "proposed", "assignment": None,
                      "duplicate_family_review": "pending", "approved": False}}
    fingerprint = payload_digest(body)
    if previous and previous.get("packet_sha256") == fingerprint:
        return previous
    body.update(packet_sha256=fingerprint,
        revision=(previous.get("revision", 0) + 1 if previous else 1),
        supersedes=previous.get("packet_sha256") if previous else None,
        invalidates=["answer_association", "transcription", "eligibility"] if previous else [])
    return body
