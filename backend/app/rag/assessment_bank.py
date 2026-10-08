"""The frontend's authored assessment source, with the same report lifecycle."""
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.auth.database import BankQuestion, GeneratedMock
from app.rag import question_bank


def create_assessment(db, user_id, test_id):
    source = Path(__file__).resolve().parents[3] / "frontend/src/assessmentQuestions.json"
    tests = json.loads(source.read_text(encoding="utf-8"))
    test = next((t for t in tests if t["id"] == test_id), None)
    if test is None:
        raise HTTPException(404, detail="ارزیابی یافت نشد")
    signature = hashlib.sha256(json.dumps(test, sort_keys=True).encode()).hexdigest()
    major = f"assessment:{test_id}"
    title = f"assessment:{test_id}:{signature}"
    archive = db.execute(select(GeneratedMock).where(GeneratedMock.title == title,
        GeneratedMock.status == "bank_only", GeneratedMock.difficulty == "assessment")).scalar_one_or_none()
    if archive is None:
        questions = [{"_id": i + 1, "subject": test["name"], "topic": q.get("topic") or test_id,
            "text": q["question"], "options": q["options"], "answer": q["answer"],
            "verification_status": "verified"} for i, q in enumerate(test["questions"])]
        archive = GeneratedMock(student_id=0, title=title, major=major, grade="دوازدهم",
            duration_minutes=max(1, len(questions)), difficulty="assessment", status="bank_only",
            bank_scope="shared", questions=json.dumps(questions, ensure_ascii=False))
        db.add(archive); db.flush(); question_bank.index_mock(db, archive)
    source_questions = question_bank.index_mock(db, archive)
    current = {q["bank_id"]: q for q in source_questions if q.get("bank_id")}
    all_rows = db.execute(select(BankQuestion).where(BankQuestion.major == major,
        BankQuestion.owner_id == 0, BankQuestion.difficulty == "assessment",
    ).order_by(BankQuestion.id)).scalars().all()
    # Removed source questions stay in history. Corrections of current source
    # questions remain usable, while archived integral questions never return.
    topics = {key: q["topic"] for key, q in current.items()}
    rows = []
    for row in all_rows:
        parent = json.loads(row.content).get("replaces_bank_id")
        if parent in topics:
            topics[row.id] = topics[parent]
        if row.id in topics and row.status == "active" and row.verified:
            rows.append(row)
    if not rows:
        db.commit()
        raise HTTPException(409, detail="سوال‌های این ارزیابی در حال بررسی‌اند؛ درس دیگری انتخاب کن")
    questions = [{**json.loads(q.content), "topic": topics[q.id], "bank_id": q.id, "_id": i + 1}
                 for i, q in enumerate(rows)]
    mock = question_bank.create_reused_mock(db, user_id, questions, major, "دوازدهم", "assessment", max(1, len(questions)))
    mock.title = f"ارزیابی {test['name']}"
    db.commit()
    return {**{k: v for k, v in test.items() if k != "questions"}, "mock_id": mock.id,
        "questions": [{"id": q["_id"], "question": q["text"], "options": q["options"], "answer": q["answer"]} for q in questions]}
