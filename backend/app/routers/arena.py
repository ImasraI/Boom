"""
Ranked duel arena (chess.com-style) for AI-generated konkur mocks.

Flow:
  1. POST /join          -> enter the matchmaking queue (stores your Elo).
  2. GET  /status        -> polled by both players; when two compatible
                            entries exist, a match is created with a fresh
                            generated mock shared by both.
  3. POST /submit        -> score your run with konkur negative marking.
  4. GET  /{match_id}    -> match state; once both scores exist, Elo deltas
                            are computed (K=32) and the loser's rating drops.
  5. GET  /leaderboard   -> global ranking with titles/badges.
  6. GET  /me            -> your rating, title, win/loss record.

If nobody of a similar level is queued, you simply keep waiting — there
are no bots. Abandoned queue entries (tab closed mid-queue) are purged
after 30 minutes so matchmaking never pairs with a ghost.
"""

import json
import threading
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.auth.database import (
    ArenaMatch,
    ArenaQueueEntry,
    GeneratedMock,
    MockAttempt,
    SessionLocal,
    User,
    record_match_rating,
    user_elo,
)
from app.auth.deps import get_current_user, get_db
from app.auth.limits import check_ai_quota, record_ai_use
from app.rag import mock_generation
from app.routers.mocks import _score
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/arena", tags=["arena"])
logger = get_logger(__name__)

_MATCHMAKING_BAND = 300  # Elo window for pairing two queued players
_STALE_QUEUE_MINUTES = 30  # purge queue entries not polled for this long
_LOCK = threading.Lock()

# (min Elo, title, color) - first threshold reached wins.
TITLES = [
    (2200, "اسطوره", "#8B5CF6"),
    (1800, "استاد کنکور", "#A855F7"),
    (1500, "نابغه", "#3B82F6"),
    (1250, "حرفه‌ای", "#14B8A6"),
    (1050, "رنک B", "#22C55E"),
    (950, "رنک C", "#EAB308"),
    (0, "تازه‌کار", "#9CA3AF"),
]


def _title(elo: int) -> dict:
    for threshold, name, color in TITLES:
        if elo >= threshold:
            return {"name": name, "color": color}
    return {"name": "تازه‌کار", "color": "#9CA3AF"}


class JoinPayload(BaseModel):
    student: Optional[dict] = None
    topics: Optional[list] = None
    questions_per_subject: Optional[int] = None
    duration_minutes: Optional[int] = None


class SubmitPayload(BaseModel):
    answers: dict
    duration_seconds: int = 0


def _try_pair(db: Session, entry: ArenaQueueEntry, student: Optional[dict]):
    """Match two human queue entries whose ratings are within the band.

    Reserves the match atomically (lock-safe) and generates the real AI
    booklet right after, OUTSIDE the matchmaking lock: a 60-420s LLM call
    must never block other players' join/status requests.
    """
    other = (
        db.execute(
            select(ArenaQueueEntry)
            .where(ArenaQueueEntry.student_id != entry.student_id)
            .where(ArenaQueueEntry.elo.between(
                entry.elo - _MATCHMAKING_BAND,
                entry.elo + _MATCHMAKING_BAND,
            ))
            .order_by(ArenaQueueEntry.joined_at.asc())
            .limit(1)
        )
        .scalar_one_or_none()
    )
    if not other:
        return None

    match = _reserve_match(db, entry, other, student)
    # Real booklet generation in a daemon thread: join_queue holds _LOCK, and
    # an LLM call can take minutes — the lock must free up immediately so
    # other players' join/status requests never block.
    plan = mock_generation.scale_plan(
        mock_generation.default_plan((student or {}).get("major") or ""),
        divisor=3, minimum=3,
    )
    threading.Thread(
        target=_generate_duel_booklet, args=(match, plan), daemon=True,
        name=f"arena-booklet-{match.id}",
    ).start()
    return match


def _reserve_match(db: Session, entry: ArenaQueueEntry, other: ArenaQueueEntry,
                   student: Optional[dict]) -> ArenaMatch:
    """Atomically pair two queue entries and reserve a placeholder match.

    Runs under _LOCK so two joiners can never grab the same opponent; the
    (slow) booklet generation happens later, outside the lock, in
    _generate_duel_booklet. The placeholder booklet keeps /status reporting
    "matched" for both players while the real questions are generated.
    """
    plan = mock_generation.scale_plan(
        mock_generation.default_plan((student or {}).get("major") or ""),
        divisor=3, minimum=3,
    )
    questions = []
    i = 0
    for s in plan:
        for _ in range(s["questions"]):
            i += 1
            questions.append({
                "_id": i,
                "subject": s["name"],
                "topic": "",
                "text": "",
                "options": ["", "", "", ""],
                "answer": 0,
                "explanation": "",
            })

    mock = GeneratedMock(
        student_id=entry.student_id,
        title=f"دوئل رنکینگ — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        major=(student or {}).get("major") or "ریاضی فیزیک",
        grade="",
        duration_minutes=sum(s["minutes"] for s in plan) // 3 or 10,
        questions=json.dumps(questions, ensure_ascii=False),
        status="claimed",  # duel placeholder rows are never pool candidates
    )
    db.add(mock)
    db.flush()

    match = ArenaMatch(
        student_a_id=other.student_id,
        student_b_id=entry.student_id,
        mock_id=mock.id,
        status="pending",
        elo_a=other.elo,
        elo_b=entry.elo,
    )
    db.add(match)
    db.delete(other)
    db.delete(entry)
    db.commit()
    db.refresh(match)
    logger.info("Arena match %d reserved: %d vs %d (booklet generating)",
                match.id, match.student_a_id, match.student_b_id)
    return match


def _generate_duel_booklet(match: ArenaMatch, plan: list) -> None:
    """Fill the reserved duel's GeneratedMock with real AI-generated questions.

    Must be called OUTSIDE _LOCK (a real LLM call can take minutes). On
    failure the match survives with the placeholder booklet and the error is
    logged; submit scoring of an all-blank booklet yields 0 for both.
    """
    try:
        mock_db = SessionLocal()
        try:
            mock = mock_db.get(GeneratedMock, match.mock_id)
            if not mock:
                return
            questions = mock_generation.generate_booklet(
                match.student_b_id, plan, topics=[], difficulty="konkur",
            )
            if questions:
                mock.questions = json.dumps(questions, ensure_ascii=False)
                mock_db.commit()
                logger.info("Arena match %d: real booklet ready (%d questions)",
                            match.id, len(questions))
        finally:
            mock_db.close()
    except Exception:
        logger.exception("Arena match %d: booklet generation failed", match.id)


@router.post("/join")
def join_queue(
    payload: JoinPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Ranked games burn an AI-generated booklet, so they share the per-user
    # daily quota mechanism (AI_DAILY_ARENA_JOIN, .env-adjustable).
    check_ai_quota(current_user.id, "arena_join")
    with _LOCK:
        db.execute(delete(ArenaQueueEntry)
                   .where(ArenaQueueEntry.student_id == current_user.id))
        db.flush()
        entry = ArenaQueueEntry(
            student_id=current_user.id,
            elo=user_elo(db, current_user.id),
        )
        db.add(entry)
        db.flush()
        match = _try_pair(db, entry, payload.student)
        found = match is not None
        db.commit()
    # Counted only after a successful outcome: a real match OR a queue spot.
    # The 429 check above ran outside _LOCK, so a rejected joiner never
    # touched the queue at all.
    record_ai_use(current_user.id, "arena_join")
    return {
        "queued": not found,
        "match_id": match.id if match else None,
        "your_elo": user_elo(db, current_user.id),
    }


@router.get("/status")
def status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Poll while queued.

    No bot fallback: if no human opponent within the rating band is queued,
    the entry simply stays queued forever until a match is found or the
    player leaves. Abandoned entries (no status poll for 30 minutes) are
    purged so matchmaking never sees ghosts.
    """
    with _LOCK:
        stale_cutoff = datetime.utcnow() - timedelta(minutes=_STALE_QUEUE_MINUTES)
        db.execute(delete(ArenaQueueEntry)
                   .where(ArenaQueueEntry.joined_at < stale_cutoff))
        db.flush()

        entry = db.execute(
            select(ArenaQueueEntry)
            .where(ArenaQueueEntry.student_id == current_user.id)
        ).scalar_one_or_none()

        pending = db.execute(
            select(ArenaMatch)
            .where((ArenaMatch.student_a_id == current_user.id)
                   | (ArenaMatch.student_b_id == current_user.id))
            .where(ArenaMatch.status == "pending")
            .order_by(ArenaMatch.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if pending:
            if entry:
                db.delete(entry)
                db.commit()
            return {"state": "matched", "match_id": pending.id}

        if not entry:
            return {"state": "idle"}

        waited = (datetime.utcnow() - entry.joined_at).total_seconds()
        return {"state": "queued", "waited_seconds": int(waited)}


@router.post("/leave")
def leave_queue(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(delete(ArenaQueueEntry)
               .where(ArenaQueueEntry.student_id == current_user.id))
    db.commit()
    return {"left": True}


@router.post("/{match_id}/submit")
def submit(
    match_id: int,
    payload: SubmitPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    match = db.get(ArenaMatch, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="مسابقه پیدا نشد")
    if current_user.id not in (match.student_a_id, match.student_b_id):
        raise HTTPException(status_code=403, detail="این مسابقه مال تو نیست")
    if match.status == "finished":
        return {"already_finished": True}

    mock = db.get(GeneratedMock, match.mock_id) if match.mock_id else None
    if not mock:
        raise HTTPException(status_code=500, detail="دفترچه مسابقه یافت نشد")

    questions = json.loads(mock.questions)
    result = _score(questions, payload.answers)
    is_a = match.student_a_id == current_user.id
    if is_a:
        match.score_a = result["percent"]
    else:
        match.score_b = result["percent"]

    db.add(MockAttempt(
        mock_id=mock.id,
        student_id=current_user.id,
        answers=json.dumps(payload.answers, ensure_ascii=False),
        duration_seconds=payload.duration_seconds,
        score=result["percent"],
        correct=result["correct"],
        wrong=result["wrong"],
        blank=result["blank"],
    ))

    if match.score_a is not None and match.score_b is not None:
        record_match_rating(match)
        match.status = "finished"
        match.finished_at = datetime.utcnow()
        if match.score_a > match.score_b:
            match.winner_id = match.student_a_id or None
        elif match.score_b > match.score_a:
            match.winner_id = match.student_b_id or None
        db.commit()
        return {**result, "finished": True, "your_score": result["percent"]}

    db.commit()
    return {**result, "finished": False, "your_score": result["percent"]}


@router.get("/me")
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    elo = user_elo(db, current_user.id)
    matches = db.execute(
        select(ArenaMatch)
        .where((ArenaMatch.student_a_id == current_user.id)
               | (ArenaMatch.student_b_id == current_user.id))
        .where(ArenaMatch.status == "finished")
        .order_by(ArenaMatch.created_at.desc())
    ).scalars().all()
    wins = sum(1 for m in matches if m.winner_id == current_user.id)
    losses = len(matches) - wins
    return {
        "elo": elo,
        "title": _title(elo),
        "wins": wins,
        "losses": losses,
        "matches": len(matches),
    }


@router.get("/leaderboard")
def leaderboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Global ranking from the latest Elo snapshot per player."""
    rows = db.execute(
        select(ArenaMatch).where(ArenaMatch.status == "finished")
        .order_by(ArenaMatch.created_at.desc())
    ).scalars().all()
    latest: dict[int, tuple[int, ArenaMatch]] = {}
    for m in rows:
        for sid, elo in ((m.student_a_id, m.elo_a), (m.student_b_id, m.elo_b)):
            if sid and sid not in latest:
                latest[sid] = (elo, m)
    entries = []
    for sid, (elo, _m) in latest.items():
        user = db.get(User, sid)
        if not user:
            continue
        entries.append({"user_id": sid, "username": user.username, "elo": elo})
    entries.sort(key=lambda e: -e["elo"])
    out = []
    for i, e in enumerate(entries[:50], start=1):
        t = _title(e["elo"])
        out.append({**e, "rank": i, "title": t["name"], "color": t["color"],
                    "is_you": e["user_id"] == current_user.id})
    return out


@router.get("/{match_id}")
def get_match(
    match_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    match = db.get(ArenaMatch, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="مسابقه پیدا نشد")
    if current_user.id not in (match.student_a_id, match.student_b_id):
        raise HTTPException(status_code=403, detail="این مسابقه مال تو نیست")

    you_are_a = match.student_a_id == current_user.id
    opp_id = match.student_b_id if you_are_a else match.student_a_id
    opp = db.get(User, opp_id) if opp_id else None
    your_elo = match.elo_a if you_are_a else match.elo_b
    opp_elo = match.elo_b if you_are_a else match.elo_a
    your_delta = match.delta_a if you_are_a else match.delta_b
    opp_delta = match.delta_b if you_are_a else match.delta_a
    your_score = match.score_a if you_are_a else match.score_b
    opp_score = match.score_b if you_are_a else match.score_a

    return {
        "match_id": match.id,
        "status": match.status,
        "opponent": opp.username if opp else "حریف",
        "opponent_elo": opp_elo,
        "opponent_delta": opp_delta,
        "your_elo": your_elo,
        "your_delta": your_delta,
        "your_score": your_score,
        "opponent_score": opp_score,
        "won": match.status == "finished" and match.winner_id == current_user.id,
        "mock_id": match.mock_id,
        "mock": {
            "duration_minutes": (db.get(GeneratedMock, match.mock_id).duration_minutes
                                 if match.mock_id else None),
        } if match.mock_id else None,
    }
