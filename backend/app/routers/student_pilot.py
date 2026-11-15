"""Colosseum pilot, enabled by a server-side packet file."""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, StrictInt

from app.auth.deps import get_current_user

router = APIRouter(prefix="/api/student-pilot")


class Attempt(BaseModel):
    revision: str
    answers: dict[str, StrictInt | None]
    confidence: dict[str, StrictInt] = Field(default_factory=dict)


class Feedback(BaseModel):
    revision: str
    comments: dict[str, str]


def packet():
    path = os.getenv("BOOM_STUDENT_PILOT_PACKET")
    if not path:
        raise HTTPException(404, "آزمون آزمایشی در دسترس نیست")
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf8"))
    return data, source.with_suffix(".sqlite3")


def session(user, response, attempt=None, feedback=None):
    response.headers["Cache-Control"] = "private, no-store"
    data, path = packet()
    submission = attempt if attempt is not None else feedback
    if submission is not None and submission.revision != data["revision"]:
        raise HTTPException(409, "نسخهٔ آزمون تغییر کرده است. آزمون را دوباره باز کنید.")
    questions = data["questions"]
    ids = {q["id"] for q in questions}
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS attempts (
            pilot TEXT, student INTEGER, answers TEXT, confidence TEXT,
            feedback TEXT, PRIMARY KEY (pilot, student))""")
        key = (data["revision"], user.id)
        if attempt is not None:
            if (set(attempt.answers) != ids
                    or any(x is not None and x not in range(4) for x in attempt.answers.values())
                    or not set(attempt.confidence) <= ids
                    or any(x not in range(1, 5) for x in attempt.confidence.values())):
                raise HTTPException(422, "پاسخ یا میزان اطمینان معتبر نیست")
            db.execute("INSERT OR IGNORE INTO attempts VALUES (?, ?, ?, ?, NULL)",
                       (*key, json.dumps(attempt.answers), json.dumps(attempt.confidence)))
        if feedback is not None:
            if not set(feedback.comments) <= ids or any(len(x) > 1000 for x in feedback.comments.values()):
                raise HTTPException(422, "بازخورد معتبر نیست")
            saved = db.execute("UPDATE attempts SET feedback=? WHERE pilot=? AND student=?",
                               (json.dumps(feedback.comments), *key))
            if not saved.rowcount:
                raise HTTPException(409, "ابتدا پاسخ‌ها را ثبت کنید")
        row = db.execute("SELECT answers, confidence, feedback FROM attempts WHERE pilot=? AND student=?", key).fetchone()
    return {
        "revision": data["revision"],
        "questions": questions if row else [
            {k: q[k] for k in ("id", "text", "options", "figure") if k in q} for q in questions
        ],
        "answers": json.loads(row[0]) if row else None,
        "feedback": json.loads(row[2]) if row and row[2] else {},
    }


@router.get("")
def open_pilot(response: Response, user=Depends(get_current_user)):
    return session(user, response)


@router.post("/submit")
def submit_pilot(body: Attempt, response: Response, user=Depends(get_current_user)):
    return session(user, response, attempt=body)


@router.post("/feedback")
def review_pilot(body: Feedback, response: Response, user=Depends(get_current_user)):
    return session(user, response, feedback=body)
