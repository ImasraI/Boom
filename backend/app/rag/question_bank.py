"""Verified reusable questions, independent of immutable exam snapshots.

Only shared corpus questions and the current student's own questions can be
assembled. A reported question is excluded from every subsequent selection.
"""
import hashlib
import json

from sqlalchemy import select, update, func, or_
from sqlalchemy.dialects.sqlite import insert

from app.auth.database import BankQuestion, GeneratedMock, QuestionReport


def grade_number(value):
    text = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    return next((n for n, name in ((12, "دوازدهم"), (11, "یازدهم"), (10, "دهم"))
                 if name in text or str(n) in text), 12)


def _valid(q):
    return (isinstance(q, dict) and bool(str(q.get("text") or "").strip())
            and isinstance(q.get("options"), list) and len(q["options"]) == 4
            and all(isinstance(o, str) and o.strip() for o in q["options"])
            and type(q.get("answer")) is int and 0 <= q["answer"] < 4)


def _fingerprint(q, owner, category="mock"):
    # Presentation ids and verification flags do not change question identity.
    content = [owner, category, q.get("subject"), q.get("text"), q.get("options"), q.get("answer")]
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def index_mock(db, mock):
    """Idempotent lazy migration; no provider requests or application DB swap."""
    try:
        questions = json.loads(mock.questions or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(questions, list):
        return []
    if mock.bank_indexed:
        return questions
    if mock.status == "pending_use" and mock.student_id == 0:
        mock.bank_scope = "shared"
    owner = 0 if mock.bank_scope == "shared" else mock.student_id
    changed = False
    for q in questions:
        if not _valid(q):
            continue  # Never index a live-generation placeholder.
        if q.get("bank_id") and db.get(BankQuestion, q["bank_id"]) is not None:
            changed = True
            continue
        fingerprint = _fingerprint(q, owner, "assessment" if mock.difficulty == "assessment" else "mock")
        stored = {k: v for k, v in q.items() if k not in ("bank_id", "_id", "id")}
        db.execute(insert(BankQuestion).values(
            fingerprint=fingerprint, owner_id=owner, major=mock.major or "",
            grade=mock.grade or "", grade_level=grade_number(mock.grade),
            difficulty="konkur" if mock.difficulty == "duel" else (mock.difficulty or "konkur"),
            subject=q.get("subject") or "سایر", topic=q.get("topic") or "",
            content=json.dumps(stored, ensure_ascii=False),
            verified=q.get("verification_status") == "verified", status="active",
            uses=0 if mock.status in ("pending_use", "bank_only") else 1, admin_note="",
        ).on_conflict_do_nothing(index_elements=["fingerprint"]))
        row = db.execute(select(BankQuestion).where(BankQuestion.fingerprint == fingerprint)).scalar_one()
        q["bank_id"] = row.id
        changed = True
    if changed:
        mock.questions = json.dumps(questions, ensure_ascii=False)
        mock.bank_indexed = True
        db.flush()
    return questions


def active_questions(db, mock):
    questions = index_mock(db, mock)
    ids = [q["bank_id"] for q in questions if isinstance(q, dict) and q.get("bank_id")]
    blocked = set(db.execute(select(BankQuestion.id).where(
        BankQuestion.id.in_(ids), BankQuestion.status != "active")).scalars()) if ids else set()
    return [q for q in questions if isinstance(q, dict) and q.get("bank_id") not in blocked]


def mark_used(db, questions):
    ids = {q["bank_id"] for q in questions if q.get("bank_id")}
    if ids:
        db.execute(update(BankQuestion).where(BankQuestion.id.in_(ids)).values(uses=BankQuestion.uses + 1))


def migrate_eligible(db, user_id, majors):
    # Shared legacy pending rows retain their provenance before being claimed.
    # Older private booklets are reusable only by their original student.
    rows = db.execute(select(GeneratedMock).where(
        GeneratedMock.bank_indexed == False,
        GeneratedMock.status.in_(("pending_use", "claimed")),
        GeneratedMock.major.in_(majors),
        or_(GeneratedMock.bank_scope == "shared", GeneratedMock.student_id.in_((0, user_id))),
    ).order_by(GeneratedMock.id)).scalars()
    for mock in rows:
        index_mock(db, mock)


def assemble(db, user_id, plan, majors, difficulty="konkur", grade="", topics=None,
             *, prefer_used=True, used_only=False, allow_partial=False, shared_only=False,
             unused_only=False, exclude_ids=()):
    """Select real verified rows. No replacement of previously assigned exams."""
    migrate_eligible(db, user_id, majors)
    query = select(BankQuestion).where(
        BankQuestion.status == "active", BankQuestion.verified == True,
        BankQuestion.major.in_(majors), BankQuestion.difficulty == difficulty,
        BankQuestion.grade_level <= grade_number(grade),
        BankQuestion.owner_id.in_((0,) if shared_only else (0, user_id)),
    )
    if used_only:
        query = query.where(BankQuestion.uses > 0)
    if unused_only:
        query = query.where(BankQuestion.uses == 0)
    if exclude_ids:
        query = query.where(BankQuestion.id.not_in(exclude_ids))
    order = (BankQuestion.uses > 0).desc() if prefer_used else (BankQuestion.uses == 0).desc()
    wanted_topics = [str(t).strip().casefold() for t in (topics or []) if str(t).strip()]
    out = []
    selected = set()
    for row in plan:
        selection = query.where(BankQuestion.subject == row["name"])
        # Ranked plans carry subject-specific study filters. A physics tick
        # selects physics questions, not lessons literally named "physics".
        # A geometry tick still restricts the math row, never the physics row.
        row_topics = ([str(t).strip().casefold() for t in row['topics']
                       if str(t).strip() and str(t).strip() != row['name']]
                      if 'topics' in row else wanted_topics)
        if row_topics:
            selection = selection.where(or_(*(BankQuestion.topic.contains(t, autoescape=True) for t in row_topics)))
        if selected:
            selection = selection.where(BankQuestion.id.not_in(selected))
        chosen = db.execute(selection.order_by(order, BankQuestion.uses.asc(), BankQuestion.id.desc())
            .limit(int(row["questions"]))).scalars().all()
        if len(chosen) < int(row["questions"]) and not allow_partial:
            return []
        for q in chosen:
            content = json.loads(q.content)
            out.append({**content, "bank_id": q.id, "_id": len(out) + 1, "verification_status": "verified"})
            selected.add(q.id)
    return out


def create_reused_mock(db, user_id, questions, major, grade, difficulty, duration, *, ranked=False):
    ids = [q["bank_id"] for q in questions if q.get("bank_id")]
    private = bool(ids and db.scalar(select(BankQuestion.id).where(BankQuestion.id.in_(ids),
        BankQuestion.owner_id != 0).limit(1)))
    mock = GeneratedMock(student_id=user_id, title="دوئل از بانک سوال" if ranked else "تمرین از بانک سوال",
        major=major, grade=grade, difficulty=difficulty, duration_minutes=duration,
        questions=json.dumps(questions, ensure_ascii=False), status="claimed",
        bank_scope="shared" if ranked and not private else "private", bank_indexed=True)
    db.add(mock)
    mark_used(db, questions)
    db.flush()
    return mock


def record_report(db, mock, user_id, question_id, reason):
    from fastapi import HTTPException
    questions = index_mock(db, mock)
    q = next((q for q in questions if str(q.get("_id") or q.get("id")) == str(question_id)), None)
    if not q or not q.get("bank_id"):
        raise HTTPException(404, detail="سوال یافت نشد")
    bank = db.get(BankQuestion, q["bank_id"])
    # Keep the source record and all unaffected questions; never erase a booklet.
    if bank.status != "deleted":
        bank.status = "corrupt"
    db.execute(insert(QuestionReport).values(question_id=bank.id, student_id=user_id, mock_id=mock.id,
        reason=reason).on_conflict_do_nothing(index_elements=["question_id", "student_id", "mock_id"]))
    db.commit()
    return {"ok": True, "question_id": bank.id, "status": bank.status}


def counts(db):
    return dict(db.execute(select(BankQuestion.status, func.count(BankQuestion.id)).group_by(BankQuestion.status)).all())
