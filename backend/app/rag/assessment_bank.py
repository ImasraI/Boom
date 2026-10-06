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
    major = f"assessment:{test_id}"
    signature = hashlib.sha256(json.dumps(test, sort_keys=True).encode()).hexdigest()
    title = f"assessment:{test_id}:{signature}"
    archive = db.execute(select(GeneratedMock).where(GeneratedMock.title == title,
        GeneratedMock.status == "bank_only", GeneratedMock.difficulty == "assessment")).scalar_one_or_none()
    if archive is None:
        questions = [{"_id": i + 1, "subject": test["name"], "topic": test_id,
            "text": q["question"], "options": q["options"], "answer": q["answer"],
            "verification_status": "verified"} for i, q in enumerate(test["questions"])]
        archive = GeneratedMock(student_id=0, title=title, major=major, grade="دوازدهم",
            duration_minutes=max(1, len(questions)), difficulty="assessment", status="bank_only",
            bank_scope="shared", questions=json.dumps(questions, ensure_ascii=False))
        db.add(archive); db.flush(); question_bank.index_mock(db, archive)
    rows = db.execute(select(BankQuestion).where(BankQuestion.major == major,
        BankQuestion.owner_id == 0, BankQuestion.difficulty == "assessment",
        BankQuestion.status == "active", BankQuestion.verified == True).order_by(BankQuestion.id)).scalars().all()
    if not rows:
        db.commit()
        raise HTTPException(409, detail="سوال‌های این ارزیابی در حال بررسی‌اند؛ درس دیگری انتخاب کن")
    questions = [{**json.loads(q.content), "bank_id": q.id, "_id": i + 1} for i, q in enumerate(rows)]
    mock = question_bank.create_reused_mock(db, user_id, questions, major, "دوازدهم", "assessment", max(1, len(questions)))
    mock.title = f"ارزیابی {test['name']}"
    db.commit()
    return {**{k: v for k, v in test.items() if k != "questions"}, "mock_id": mock.id,
        "questions": [{"id": q["_id"], "question": q["text"], "options": q["options"], "answer": q["answer"]} for q in questions]}
