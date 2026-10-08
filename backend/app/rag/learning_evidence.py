"""Answered, verified questions are evidence; abandoned exams are not mistakes."""
import json
from datetime import datetime, timedelta

from sqlalchemy import select
from app.auth.database import BankQuestion, GeneratedMock, MockAttempt, StudentProfile, WrongAnswer


def _decode(value, fallback):
    try:
        result = json.loads(value) if isinstance(value, str) else value
        return result if isinstance(result, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def option(value):
    # Option zero is a real selection; booleans and malformed payloads are not.
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= 3:
        return value
    if isinstance(value, str) and value in ("0", "1", "2", "3"):
        return int(value)
    return None


def answer_events(db, user_id, *, days=90, trusted_only=True):
    statement = select(MockAttempt, GeneratedMock).join(
        GeneratedMock, MockAttempt.mock_id == GeneratedMock.id).where(MockAttempt.student_id == user_id)
    if days is not None:
        statement = statement.where(MockAttempt.created_at >= datetime.utcnow() - timedelta(days=days))
    attempts = db.execute(statement).all()
    ids = {q.get("bank_id") for _, mock in attempts for q in _decode(mock.questions, [])
           if isinstance(q, dict) and q.get("bank_id")}
    active = set(db.scalars(select(BankQuestion.id).where(
        BankQuestion.id.in_(ids), BankQuestion.status == "active", BankQuestion.verified.is_(True),
        BankQuestion.owner_id.in_([0, user_id])))) if ids else set()
    events = []
    for attempt, mock in attempts:
        answers = _decode(attempt.answers, {})
        for question in _decode(mock.questions, []):
            if not isinstance(question, dict):
                continue
            if trusted_only and (question.get("verification_status") != "verified" or
                    (question.get("bank_id") and question["bank_id"] not in active)):
                continue
            expected = option(question.get("answer"))
            if expected is None:
                continue
            selected = option(answers.get(str(question.get("_id", question.get("id")))))
            events.append({"subject": question.get("subject") or "عمومی",
                "topic": question.get("topic") or "", "book": question.get("book") or "",
                "page": question.get("page"), "source": "mock", "created_at": attempt.created_at,
                "was_blank": selected is None,
                "outcome": "blank" if selected is None else "correct" if selected == expected else "wrong"})
    return events


def manual_events(db, user_id, *, days=90):
    statement = select(WrongAnswer).where(WrongAnswer.student_id == user_id)
    if days is not None:
        statement = statement.where(WrongAnswer.created_at >= datetime.utcnow() - timedelta(days=days))
    events = []
    for row in db.scalars(statement):
        # Mock/arena copies are represented by the verified attempt, never twice.
        selected = (row.student_answer or "").strip()
        if row.source in ("mock", "arena") or row.was_blank or not selected:
            continue
        if selected == (row.correct_answer or "").strip():
            continue
        events.append({"subject": row.subject, "topic": row.topic or "", "book": row.book or "",
            "page": row.page, "source": "practice", "created_at": row.created_at,
            "was_blank": False, "outcome": "wrong"})
    return events


def curriculum_events(db, user_id, *, days=90):
    from app.rag.knowledge_graph import curriculum_lookup
    from app.rag.book_curriculum import norm
    profile = db.query(StudentProfile).filter_by(user_id=user_id).first()
    lookup = curriculum_lookup(profile.major if profile and profile.major else "ریاضی فیزیک")
    result = []
    for event in answer_events(db, user_id, days=days) + manual_events(db, user_id, days=days):
        canonical = lookup.get((norm(event["subject"]), norm(event["topic"])))
        if canonical:
            result.append({**event, "subject": canonical[0], "topic": canonical[1]})
    return sorted(result, key=lambda e: e["created_at"] or datetime.min, reverse=True)


def confirmed_mistakes(db, user_id, *, days=90):
    return [event for event in curriculum_events(db, user_id, days=days) if event["outcome"] == "wrong"]
