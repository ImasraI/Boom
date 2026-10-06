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
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.auth.database import (
    ArenaMatch,
    ArenaQueueEntry,
    ArenaScheduledInvite,
    BankQuestion,
    GeneratedMock,
    MockAttempt,
    SessionLocal,
    StudentProfile,
    User,
    record_match_rating,
    user_elo,
)
import random as _random
from app.auth.deps import get_current_user, get_db
from app.auth.limits import consume_ai_use, feature_quota, release_ai_use
from app.rag import knowledge_base as kb, mock_generation, pool_core
from app.rag.konkur_format import major_key
from app.rag.provider_quota import DAILY_QUOTA_MESSAGE, pool_quota_status, require_pool_available
from app.routers.mocks import _score
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/arena", tags=["arena"])
logger = get_logger(__name__)

_MATCHMAKING_BAND = 300  # Elo window for pairing two queued players (base)
_BAND_WIDEN_PER_MIN = 50  # +Elo per queued minute (see _matchmaking_band)
_BAND_MAX = 900  # widened band never grows past this
_STALE_QUEUE_MINUTES = 30  # purge queue entries not polled for this long
_LOCK = threading.Lock()
# How many Elo-compatible queue entries one pairing attempt inspects before
# giving up: a player whose filter excludes the oldest candidates must still
# find a compatible one further down the queue.
_MAX_PAIR_CANDIDATES = 25

# --- AI-rival fallback (NON-RANKED exhibition track) -----------------------
# /status offers the AI rival once the player has queued this long with no
# human match; the player must explicitly opt in via POST /ai-rival.
_AI_RIVAL_OFFER_AFTER_SECONDS = 20
# Named rival difficulties. accuracy = per-question hit probability of the
# simulated opponent; elo = the fixed rating the UI shows for that rival.
# "رتبه زیر ۱۰۰۰ کشوری" models last year's top-1000 ranks: ~78% correct.
_AI_RIVAL_LEVELS = {
    "top1000": {"fa": "رقیب رتبه زیر ۱۰۰۰ کشوری", "accuracy": 0.78, "elo": 1850},
    "top5000": {"fa": "رقیب رتبه زیر ۵۰۰۰ کشوری", "accuracy": 0.64, "elo": 1400},
    "top20000": {"fa": "رقیب رتبه زیر ۲۰ هزار کشوری", "accuracy": 0.45, "elo": 1000},
}
_AI_RIVAL_NAME = "رقیب هوش مصنوعی"

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


def _major_key_of(major_label: str) -> str:
    """Frontend/DB major label -> konkur_format key (for pool shelves)."""
    try:
        return major_key(major_label or "")
    except Exception:
        return "riazi"


def _sample_rival_answers(mock: GeneratedMock, accuracy: float) -> dict:
    """Simulate the AI rival's per-question answers against `accuracy`.

    For every booklet question, sample Bernoulli(accuracy): on a hit the
    rival picks the stored correct option; on a miss it picks uniformly from
    the three wrong options (never blank - the rival always finishes).
    Returns {question_id: option_index}. Stored as match.ai_answers JSON, so
    submit scores the simulated answers through the SAME negative-marking
    _score() path as a human's - no scoring fork, no favoritism.
    """
    rng = _random.Random()
    out = {}
    try:
        questions = json.loads(mock.questions or "[]")
    except (ValueError, TypeError):
        questions = []
    for q in questions:
        qid = q.get("_id") or q.get("id")
        answer = q.get("answer")
        if qid is None or not isinstance(answer, int) or not 0 <= answer <= 3:
            continue
        if rng.random() < accuracy:
            out[str(qid)] = answer
        else:
            wrong = [i for i in range(4) if i != answer]
            out[str(qid)] = rng.choice(wrong)
    return out


class JoinPayload(BaseModel):
    student: Optional[dict] = None
    topics: Optional[list] = None
    questions_per_subject: Optional[int] = None
    duration_minutes: Optional[int] = None
    # Study subjects the player wants to be tested on (arena filter ticks).
    # Not exam topics: each tick also constrains WHO can be matched, since
    # the opponent must study every ticked subject.
    wanted: Optional[list] = None


class SubmitPayload(BaseModel):
    answers: dict
    duration_seconds: int = 0


class AiRivalPayload(BaseModel):
    rival: str = Field(pattern="^(top1000|top5000|top20000)$")
    student: Optional[dict] = None


class ScheduleInvitePayload(BaseModel):
    """Create a scheduled-duel offer: kickoff time + optional subject ticks."""
    # ISO timestamp (UTC, naive or with offset) of the kickoff.
    starts_at: str
    wanted: Optional[list] = None
    student: Optional[dict] = None


def _profile_of(db: Session, user_id: int) -> Optional[StudentProfile]:
    """The student's server-side profile row (None when never created)."""
    return db.execute(
        select(StudentProfile).where(StudentProfile.user_id == user_id)
    ).scalar_one_or_none()


def _knowledge_base(db: Session, user_id: int,
                    student: Optional[dict]) -> tuple:
    """(major, grade) of a queued player - what we may test them on.

    The server-side profile is authoritative (growth-readiness project 1);
    the client's cached profile only fills gaps. This matters: matchmaking
    used to build EVERY duel booklet from a hardcoded ریاضی فیزیک plan,
    because Arena's join request sends no student at all.
    """
    major = grade = ""
    profile = _profile_of(db, user_id)
    if profile is not None:
        major = (profile.major or "").strip()
        grade = (profile.grade or "").strip()
    major = major or str((student or {}).get("major") or "").strip()
    grade = grade or str((student or {}).get("grade") or "").strip()
    return major or "ریاضی فیزیک", grade


def _wanted_of(entry: ArenaQueueEntry) -> list:
    """The tick list stored on a queue entry (never raises on junk)."""
    try:
        raw = json.loads(entry.wanted or "[]")
    except (ValueError, TypeError):
        raw = []
    return [str(s) for s in raw] if isinstance(raw, list) else []


def _try_pair(db: Session, entry: ArenaQueueEntry):
    """Match two queue entries whose ratings AND knowledge bases fit.

    Pairing needs a shared exam skeleton, not just a close rating: the
    booklet is generated from the INTERSECTION of both players' subjects
    (see rag/knowledge_base.py), so a ریاضی فیزیک student is paired with a
    علوم تجربی one on ریاضی/فیزیک/شیمی, and someone who ticked هندسه never
    gets a علوم تجربی opponent (whose subject list has no هندسه). Candidates
    that cannot duel this player are skipped - the entry simply keeps
    waiting, exactly like an out-of-band rating.

    Reserves the match atomically (lock-safe) and fills the booklet from the
    pre-generated duel pool when one is available; only otherwise does it
    start a live LLM generation, OUTSIDE the matchmaking lock: a 60-420s LLM
    call must never block other players' join/status requests.
    """
    band = _matchmaking_band(entry)
    candidates = (
        db.execute(
            select(ArenaQueueEntry)
            .where(ArenaQueueEntry.student_id != entry.student_id)
            .where(ArenaQueueEntry.elo.between(entry.elo - band, entry.elo + band))
            .order_by(ArenaQueueEntry.joined_at.asc())
            .limit(_MAX_PAIR_CANDIDATES)
        )
        .scalars()
        .all()
    )
    mine = _wanted_of(entry)
    other = None
    pair = None
    for candidate in candidates:
        verdict = kb.pair_plan(entry.major or "", candidate.major or "",
                               mine, _wanted_of(candidate))
        if verdict["ok"]:
            other, pair = candidate, verdict
            break
        logger.info(
            "Arena: skipping queued user %s (major=%s) - %s",
            candidate.student_id, candidate.major, verdict["reason"],
        )
    if other is None or pair is None:
        return None

    grade = kb.grade_scope(entry.grade or "", other.grade or "")
    match = _reserve_match(db, entry, other, pair, grade)
    if match.mock_ready:
        # Served instantly from the pre-generated duel pool.
        return match
    # Live generation fallback in a daemon thread: join_queue holds _LOCK, and
    # an LLM call can take minutes — the lock must free up immediately so
    # other players' join/status requests never block.
    threading.Thread(
        target=_generate_duel_booklet, args=(match, pair["plan"]),
        kwargs={"topics": pair["topics"], "grade": grade},
        daemon=True, name=f"arena-booklet-{match.id}",
    ).start()
    return match


def _matchmaking_band(entry: ArenaQueueEntry) -> int:
    """Elo pairing window, widening with queue wait: 300 at join, +50 every
    full minute queued, capped at 900 so a long-waiting player eventually
    matches instead of queueing forever. waited_seconds is already surfaced
    by /status, so both sides agree on the same clock."""
    waited = 0.0
    try:
        joined = entry.joined_at
        if joined is not None:
            if joined.tzinfo is None:
                joined = joined.replace(tzinfo=timezone.utc)
            waited = (datetime.now(timezone.utc) - joined).total_seconds()
    except Exception:
        waited = 0.0
    return min(900, _MATCHMAKING_BAND + 50 * int(max(0.0, waited) // 60))


def _reserve_match(db: Session, entry: ArenaQueueEntry, other: ArenaQueueEntry,
                   pair: dict, grade: str = "") -> ArenaMatch:
    """Atomically pair two queue entries and reserve a placeholder match.

    Runs under _LOCK so two joiners can never grab the same opponent. A
    pre-generated + verified duel booklet is claimed from the pool when the
    duel is a plain SAME-MAJOR one with no tick filter (the only shape the
    per-major shelves hold); a cross-major duel has its own intersection
    plan, so a placeholder booklet is stored and the (slow) live generation
    happens later, outside the lock, in _generate_duel_booklet. Either way
    /status reports "matched" for both players immediately.
    """
    plan = pair["plan"]
    same_major = _major_key_of(entry.major or "") == _major_key_of(other.major or "")
    unfiltered = not _wanted_of(entry) and not _wanted_of(other)

    # Fast path: a pre-generated, already-verified duel booklet.
    pooled = None
    if same_major and unfiltered:
        pooled = pool_core.claim_duel_booklet(
            db, entry.student_id, other.student_id,
            _major_key_of(entry.major or ""), grade=grade)
    if pooled is None:
        pooled = pool_core.reused_duel(db, entry.student_id, _major_key_of(entry.major or ""),
            grade=grade, plan=plan, topics=pair.get("topics"))
    if pooled is not None:
        mock = pooled
        logger.info("Arena match served from duel pool (mock %d).", mock.id)
    else:
        require_pool_available()  # No network call; never reserve an unplayable daily-quota match.
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
        shared = "، ".join(pair["booklet_subjects"])
        mock = GeneratedMock(
            student_id=entry.student_id,
            title=(f"دوئل رقابتی — {shared} — "
                   f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"),
            major=entry.major or "ریاضی فیزیک",
            grade=grade,
            duration_minutes=kb.duel_duration_minutes(plan),
            questions=json.dumps(questions, ensure_ascii=False),
            status="claimed",  # duel placeholder rows are never pool candidates
        )
        db.add(mock)
        db.flush()
    mock_ready = not any(not (q.get("text") or "").strip()
                         for q in (json.loads(mock.questions or "[]")))

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
    match.mock_ready = mock_ready
    logger.info("Arena match %d reserved: %d vs %d (%s)",
                match.id, match.student_a_id, match.student_b_id,
                "pool booklet" if mock_ready else "booklet generating")
    return match


def _generate_duel_booklet(match: ArenaMatch, plan: list,
                           topics: Optional[list] = None,
                           grade: str = "") -> None:
    """Fill the reserved duel's GeneratedMock with real AI-generated questions.

    Must be called OUTSIDE _LOCK (a real LLM call can take minutes). On
    failure the match is cancelled without rating changes. Empty placeholders
    must never leave either player waiting indefinitely or be scored.

    `plan` is the duel's intersection plan (knowledge_base.pair_plan),
    `topics` the players' ticked subjects (they also steer the questions
    inside their booklet subject) and `grade` the younger player's grade, so
    the booklet never leaves the syllabus both players have reached.

    Duel booklets get the SAME answer-verification pass as pool booklets:
    a wrong key in a ranked duel directly moves Elo, so an unverified
    generation is never stored. Tighter budget than the pool default so the
    duel's already-long generation does not grow much more.
    """
    try:
        mock_db = SessionLocal()
        try:
            current = mock_db.get(ArenaMatch, match.id)
            if not current or current.status == "cancelled":
                return
            mock = mock_db.get(GeneratedMock, match.mock_id)
            if not mock:
                raise ValueError("Missing duel booklet")
            require_pool_available()
            questions = mock_generation.generate_booklet(
                match.student_b_id, plan, topics=list(topics or []),
                difficulty="konkur", grade=grade,
            )
            if questions:
                questions = mock_generation.verify_and_repair_booklet(
                    questions, match.student_b_id,
                    difficulty="konkur", max_regens=1, timeout=45.0,
                )
                mock_db.refresh(current)
                if current.status == "cancelled":
                    return
                mock.questions = json.dumps(questions, ensure_ascii=False)
                mock.bank_indexed = False
                from app.rag import question_bank
                question_bank.index_mock(mock_db, mock)
                complete = pool_core.verified_booklet(mock.questions) and all(
                    sum(q.get("subject") == row["name"] for q in questions) == row["questions"] for row in plan)
                if not complete:
                    mock.status = "bank_only"  # Preserve verified survivors for the owner's practice.
                    raise ValueError("Incomplete verified duel booklet")
                mock_db.commit()
                logger.info("Arena match %d: verified booklet ready (%d questions)",
                            match.id, len(questions))
            else:
                raise ValueError("No verified duel questions")
        except Exception:
            if not mock_db.is_active:
                mock_db.rollback()
            current = mock_db.get(ArenaMatch, match.id)
            if current and current.status in ("pending", "scheduled"):
                current.status = "cancelled"
                current.generation_error = (DAILY_QUOTA_MESSAGE if pool_quota_status()["blocked"]
                    else "ساخت و بررسی سوال‌های مسابقه ناموفق بود؛ مسابقه بدون تغییر رتبه لغو شد.")
                current.delta_a = current.delta_b = 0
                current.finished_at = datetime.utcnow()
                mock_db.commit()
            logger.warning("Arena match %d: booklet generation cancelled", match.id)
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
    if pool_quota_status()["blocked"]:
        # Do not queue a player when neither generation nor any verified
        # shared stock can supply a match. Legacy indexed/not-yet-indexed
        # booklets remain eligible; private practice questions are not shared.
        shared = db.scalar(select(BankQuestion.id).where(BankQuestion.owner_id == 0,
            BankQuestion.verified == True, BankQuestion.status == "active").limit(1))
        raw_stock = db.execute(select(GeneratedMock.questions).where(
            (GeneratedMock.bank_scope == "shared") | ((GeneratedMock.student_id == 0)
                & (GeneratedMock.status == "pending_use")),
            GeneratedMock.difficulty.in_(("konkur", pool_core.DUEL_DIFFICULTY)))).scalars()
        if not shared and not any(pool_core.verified_booklet(raw) for raw in raw_stock):
            require_pool_available()
    # Ranked games burn an AI-generated booklet, so they share the per-user
    # daily quota mechanism (AI_DAILY_ARENA_JOIN, .env-adjustable).
    # Atomic reserve (was check-then-record: concurrent joins blew the cap).
    consume_ai_use(current_user.id, "arena_join")
    # Knowledge base first (profile row + the client's cached profile): the
    # queue entry must remember what this player may be tested on, because
    # the opponent's entry is the only thing matchmaking can compare it with.
    major, grade = _knowledge_base(db, current_user.id, payload.student)
    wanted = kb.clean_wanted(major, payload.wanted)
    ignored = [str(s).strip() for s in (payload.wanted or [])
               if str(s).strip() and str(s).strip() not in wanted]
    if ignored:
        logger.info("Arena: user %s ticked subjects outside their major %r: %r",
                    current_user.id, major, ignored)
    try:
        with _LOCK:
            db.execute(delete(ArenaQueueEntry)
                       .where(ArenaQueueEntry.student_id == current_user.id))
            db.flush()
            entry = ArenaQueueEntry(
                student_id=current_user.id,
                elo=user_elo(db, current_user.id),
                major=major,
                grade=grade,
                wanted=json.dumps(wanted, ensure_ascii=False),
            )
            db.add(entry)
            db.flush()
            match = _try_pair(db, entry)
            found = match is not None
            db.commit()
    except Exception:
        db.rollback()
        release_ai_use(current_user.id, "arena_join")
        raise
    # Counted only after a successful outcome: a real match OR a queue spot.
    # The 429 check above ran outside _LOCK, so a rejected joiner never
    # touched the queue at all.
    return {
        "queued": not found,
        "match_id": match.id if match else None,
        "your_elo": user_elo(db, current_user.id),
        "major": major,
        "wanted": wanted,
        "ignored_wanted": ignored,
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

        # Scheduled duels whose kickoff has arrived become playable now.
        _activate_due_matches(db, current_user.id)
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

        # A booked duel surfaces in EVERY state (matched/queued/idle) so the
        # lobby can show the countdown - including while fully idle, which the
        # old early-return below silently skipped.
        upcoming = _upcoming_scheduled(db, current_user.id)
        upcoming_view = None
        if upcoming:
            invite, match = upcoming
            opp_id = (match.student_b_id if match.student_a_id == current_user.id
                      else match.student_a_id)
            opp = db.get(User, opp_id) if opp_id else None
            upcoming_view = {
                "match_id": match.id,
                "opponent": opp.username if opp else "—",
                "starts_at": invite.starts_at.isoformat(),
                "seconds_until": int((invite.starts_at - datetime.utcnow()).total_seconds()),
                "status": match.status,
            }

        if pending:
            if entry:
                db.delete(entry)
                db.commit()
            resp = {"state": "matched", "match_id": pending.id}
            if upcoming_view:
                resp["upcoming_scheduled"] = upcoming_view
            return resp

        if not entry:
            resp = {"state": "idle"}
            if upcoming_view:
                resp["upcoming_scheduled"] = upcoming_view
            return resp

        waited = (datetime.utcnow() - entry.joined_at).total_seconds()
        base = {"state": "queued", "waited_seconds": int(waited),
                "band": _matchmaking_band(entry),
                "major": entry.major,
                "wanted": _wanted_of(entry),
                "ai_offer": waited >= _AI_RIVAL_OFFER_AFTER_SECONDS,
                "ai_rivals": [
                    {"key": k, "name": v["fa"], "elo": v["elo"]}
                    for k, v in _AI_RIVAL_LEVELS.items()
                ]}
    if upcoming_view:
        base["upcoming_scheduled"] = upcoming_view
    return base


@router.post("/ai-rival")
def create_ai_rival_match(
    payload: AiRivalPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Leave the human queue and start an AI-rival EXHIBITION match.

    Explicit opt-in after /status sets ai_offer=true. The opponent's
    per-question answers are sampled against the named level's accuracy and
    STORED on the match row, so scoring runs identically to a real duel.
    These rows are hard-flagged is_ai_opponent=True and are excluded from
    Elo, placement K, /me and the leaderboard everywhere (see the guard in
    record_match_rating and the filters in this module).

    The booklet comes from the pre-generated duel pool when available (same
    shelf real duels use); only an empty shelf falls back to a live
    generation thread, exactly like human matchmaking.
    """
    level = _AI_RIVAL_LEVELS.get(payload.rival)
    if not level:
        raise HTTPException(status_code=400, detail="سطح رقیب نامعتبر است")
    # Atomic reserve (was check-then-record: concurrent joins blew the cap).
    consume_ai_use(current_user.id, "arena_join")
    with _LOCK:
        db.execute(delete(ArenaQueueEntry)
                   .where(ArenaQueueEntry.student_id == current_user.id))
        db.flush()
        student = payload.student or {}
        major, grade = _knowledge_base(db, current_user.id, student)
        # An exhibition is always a SAME-major duel against a simulated
        # opponent, so its plan is the player's own booklet (identical to
        # what the per-major shelves hold: pair_plan(major, major)).
        exhibition = kb.pair_plan(major, major)
        plan = exhibition["plan"]
        major_key = _major_key_of(major)
        # Same booklet stock real duels draw from (row owned by the player,
        # opponent_b = None is fine - the pool only needs both ids for the
        # seen-before filter, and an exhibition has no second player yet).
        pooled = pool_core.claim_duel_booklet(
            db, current_user.id, 0, major_key, grade=grade, prefer_used=True)
        if pooled is not None:
            mock = pooled
        else:
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
                student_id=current_user.id,
                title=f"مسابقه با رقیب هوش مصنوعی — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                major=major,
                grade=grade,
                duration_minutes=kb.duel_duration_minutes(plan),
                questions=json.dumps(questions, ensure_ascii=False),
                status="claimed",
            )
            db.add(mock)
            db.flush()

        match = ArenaMatch(
            student_a_id=current_user.id,
            student_b_id=0,  # sentinel: no human opponent (cf. pool POOL_OWNER_ID)
            mock_id=mock.id,
            status="pending",
            elo_a=user_elo(db, current_user.id),
            elo_b=level["elo"],  # fixed display rating for the named rival
            is_ai_opponent=True,
            ai_rival=payload.rival,
            ai_answers=json.dumps(_sample_rival_answers(mock, level["accuracy"]),
                                  ensure_ascii=False),
        )
        db.add(match)
        db.flush()
        if not pooled:
            # Live generation OUTSIDE the lock, same as human matchmaking:
            # _generate_duel_booklet re-reads the match row in its own session.
            threading.Thread(
                target=_generate_duel_booklet, args=(match, plan),
                kwargs={"grade": grade},
                daemon=True, name=f"arena-ai-booklet-{match.id}",
            ).start()
        db.commit()
        db.refresh(match)
    # Quota already reserved at entry.
    logger.info("AI-rival match %d started: user %d vs %s",
                match.id, current_user.id, payload.rival)
    return {
        "match_id": match.id,
        "ai_rival": payload.rival,
        "opponent": _AI_RIVAL_NAME,
        "opponent_elo": level["elo"],
        "mock_ready": not any(not (q.get("text") or "").strip()
                              for q in json.loads(mock.questions or "[]")),
        "your_elo": user_elo(db, current_user.id),
    }


# --- Scheduled duels (book a match, another player accepts) ---------------
# A scheduled duel is created as an OPEN INVITE anyone can book; on booking
# an ArenaMatch with status="scheduled" + starts_at is reserved and the
# booklet is claimed from the duel pool RIGHT AWAY, so nothing waits on the
# LLM at kickoff. /status lazily flips due matches to "pending"; from there
# both players walk the exact same poll -> play -> submit path as instant
# matchmaking. Elo snapshots are frozen at booking time.
_MIN_SCHEDULE_AHEAD = timedelta(minutes=5)   # no instant-respawn abuse
_MAX_SCHEDULE_AHEAD = timedelta(days=14)
# Level window for booking someone's offer (live matchmaking pairs within
# 300..900 depending on wait; a booking has no waiting room, so a fixed
# generous window keeps mismatches out without starving the list).
_SCHEDULE_ELO_BAND = 600
# An unaccepted invite whose kickoff passed this long ago stops being listed.
_SCHEDULE_STALE_GRACE = timedelta(minutes=30)


def _parse_starts_at(raw: str) -> datetime:
    """ISO string -> naive UTC datetime (the DB stores naive UTC everywhere)."""
    text = (raw or "").strip().replace("Z", "+00:00")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _new_duel_placeholder(db: Session, owner_id: int, plan: list,
                          major: str, grade: str, title: str) -> GeneratedMock:
    """A blank GeneratedMock skeleton for a duel (live generation fills it)."""
    questions = []
    i = 0
    for s in plan:
        for _ in range(s["questions"]):
            i += 1
            questions.append({
                "_id": i, "subject": s["name"], "topic": "", "text": "",
                "options": ["", "", "", ""], "answer": 0, "explanation": "",
            })
    mock = GeneratedMock(
        student_id=owner_id, title=title, major=major or "ریاضی فیزیک",
        grade=grade, duration_minutes=kb.duel_duration_minutes(plan),
        questions=json.dumps(questions, ensure_ascii=False),
        status="claimed",  # duel placeholder rows are never pool candidates
    )
    db.add(mock)
    db.flush()
    return mock


def _activate_due_matches(db: Session, user_id: int) -> None:
    """Flip this player's scheduled matches whose kickoff has arrived to
    "pending" so the normal /status matched-path picks them up.

    Lazy on purpose (the same pattern as the stale-queue purge): no cron
    needed. Runs under _LOCK from the status/get_match endpoints.
    """
    due = db.execute(
        select(ArenaMatch)
        .where((ArenaMatch.student_a_id == user_id)
               | (ArenaMatch.student_b_id == user_id))
        .where(ArenaMatch.status == "scheduled")
        .where(ArenaMatch.starts_at.isnot(None))
        .where(ArenaMatch.starts_at <= datetime.utcnow())
    ).scalars().all()
    for match in due:
        match.status = "pending"
        if due:
            logger.info("Scheduled arena match %d activated (kickoff reached).",
                        match.id)
    if due:
        db.flush()


def _upcoming_scheduled(db: Session, user_id: int):
    """The user's next booked scheduled duel ({match, invite} or None)."""
    rows = db.execute(
        select(ArenaScheduledInvite, ArenaMatch)
        .join(ArenaMatch, ArenaScheduledInvite.match_id == ArenaMatch.id)
        .where((ArenaScheduledInvite.host_id == user_id)
               | (ArenaScheduledInvite.accepted_by == user_id))
        .where(ArenaScheduledInvite.cancelled_at.is_(None))
        .where(ArenaMatch.status.in_(("scheduled", "pending")))
        .order_by(ArenaScheduledInvite.starts_at.asc())
    ).first()
    return rows


def _invite_view(db: Session, invite: ArenaScheduledInvite) -> dict:
    host = db.get(User, invite.host_id)
    return {
        "id": invite.id,
        "host": host.username if host else "—",
        "host_elo": invite.elo,
        "starts_at": invite.starts_at.isoformat(),
        "seconds_until": int((invite.starts_at - datetime.utcnow()).total_seconds()),
        "major": invite.major,
        "wanted": _wanted_of(invite),
        "is_mine": False,  # callers override for their own invites
        "accepted": invite.accepted_by is not None,
    }


@router.get("/scheduled")
def list_scheduled(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The scheduling lobby: open invites anyone can book + my upcoming
    scheduled duels (with their kickoff countdowns)."""
    now = datetime.utcnow()
    cutoff = now - _SCHEDULE_STALE_GRACE
    open_rows = db.execute(
        select(ArenaScheduledInvite)
        .where(ArenaScheduledInvite.accepted_by.is_(None))
        .where(ArenaScheduledInvite.cancelled_at.is_(None))
        .where(ArenaScheduledInvite.starts_at > cutoff)
        .order_by(ArenaScheduledInvite.starts_at.asc())
        .limit(50)
    ).scalars().all()
    mine_rows = db.execute(
        select(ArenaScheduledInvite, ArenaMatch)
        .join(ArenaMatch, ArenaScheduledInvite.match_id == ArenaMatch.id)
        .where((ArenaScheduledInvite.host_id == current_user.id)
               | (ArenaScheduledInvite.accepted_by == current_user.id))
        .where(ArenaScheduledInvite.cancelled_at.is_(None))
        .where(ArenaMatch.status.in_(("scheduled", "pending")))
        .order_by(ArenaScheduledInvite.starts_at.asc())
    ).all()
    open_list = []
    for invite in open_rows:
        view = _invite_view(db, invite)
        view["is_mine"] = invite.host_id == current_user.id
        view["can_accept"] = (
            not view["is_mine"]
            and abs(invite.elo - user_elo(db, current_user.id)) <= _SCHEDULE_ELO_BAND
        )
        open_list.append(view)
    mine_list = []
    for invite, match in mine_rows:
        opp_id = (match.student_b_id if match.student_a_id == current_user.id
                  else match.student_a_id)
        opp = db.get(User, opp_id) if opp_id else None
        mine_list.append({
            "match_id": match.id,
            "invite_id": invite.id,
            "opponent": opp.username if opp else "—",
            "opponent_elo": match.elo_b if match.student_a_id == current_user.id else match.elo_a,
            "starts_at": invite.starts_at.isoformat(),
            "seconds_until": int((invite.starts_at - now).total_seconds()),
            "status": match.status,
            "you_booked": invite.accepted_by == current_user.id,
        })
    return {
        "open": open_list,
        "mine": mine_list,
        # Live remaining quota for the scheduling UI (post-refund).
        "quota": feature_quota(current_user.id, "arena_join"),
    }


@router.post("/scheduled")
def create_scheduled(
    payload: ScheduleInvitePayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Post an open "duel at <time>" offer to the scheduling list."""
    try:
        starts_at = _parse_starts_at(payload.starts_at)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="زمان شروع نامعتبر است")
    now = datetime.utcnow()
    if starts_at < now + _MIN_SCHEDULE_AHEAD:
        raise HTTPException(status_code=422, detail="زمان شروع باید حداقل ۵ دقیقه دیگر باشد")
    if starts_at > now + _MAX_SCHEDULE_AHEAD:
        raise HTTPException(status_code=422, detail="حداکثر ۱۴ روز جلوتر می‌توان برنامه گذاشت")
    major, grade = _knowledge_base(db, current_user.id, payload.student)
    wanted = kb.clean_wanted(major, payload.wanted)
    with _LOCK:
        # One open offer per host: a second one would let one player flood
        # the list (and both would book the same acceptor's evening).
        existing = db.execute(
            select(ArenaScheduledInvite)
            .where(ArenaScheduledInvite.host_id == current_user.id)
            .where(ArenaScheduledInvite.accepted_by.is_(None))
            .where(ArenaScheduledInvite.cancelled_at.is_(None))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409,
                                detail="یک پیشنهاد باز داری؛ اول آن را لغو کن")
        invite = ArenaScheduledInvite(
            host_id=current_user.id,
            starts_at=starts_at,
            major=major,
            grade=grade,
            elo=user_elo(db, current_user.id),
            wanted=json.dumps(wanted, ensure_ascii=False),
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)
    view = _invite_view(db, invite)
    view["is_mine"] = True
    return view


def _refund_and_raise(user_id: int, status_code: int, detail: str):
    """A refused scheduled accept must not burn the acceptor's daily unit.

    consume_ai_use() reserves the arena_join unit up front (atomic
    anti-race reserve); every validation failure refunds it, so only a
    real booking counts against the daily cap.
    """
    release_ai_use(user_id, "arena_join")
    raise HTTPException(status_code=status_code, detail=detail)


@router.post("/scheduled/{invite_id}/accept")
def accept_scheduled(
    invite_id: int,
    payload: JoinPayload = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Book someone's open offer: reserve the ArenaMatch at status="scheduled"
    and pull the booklet from the duel pool NOW (no LLM wait at kickoff)."""
    # The acceptor pays the arena_join quota: the booklet is claimed for
    # them at booking time (atomic reserve, same as join). Refused accepts
    # refund it via _refund_and_raise below.
    consume_ai_use(current_user.id, "arena_join")
    with _LOCK:
        invite = db.get(ArenaScheduledInvite, invite_id)
        if not invite or invite.cancelled_at is not None:
            _refund_and_raise(current_user.id, 404, "این پیشنهاد دیگر موجود نیست")
        if invite.accepted_by is not None:
            _refund_and_raise(current_user.id, 409, "کسی قبلاً این مسابقه را رزرو کرده")
        if invite.host_id == current_user.id:
            _refund_and_raise(current_user.id, 400, "نمی‌توانی پیشنهاد خودت را رزرو کنی")
        if invite.starts_at <= datetime.utcnow():
            _refund_and_raise(current_user.id, 410, "زمان این مسابقه گذشته است")
        if abs(invite.elo - user_elo(db, current_user.id)) > _SCHEDULE_ELO_BAND:
            _refund_and_raise(current_user.id, 409,
                              "سطح تو با این مسابقه فاصله زیادی دارد")
        # Same fairness rule as live matchmaking: shared exam material.
        major, grade = _knowledge_base(db, current_user.id,
                                       (payload.student if payload else None))
        pair = kb.pair_plan(invite.major or "", major,
                            _wanted_of(invite), kb.clean_wanted(major, (payload.wanted if payload else None)))
        if not pair["ok"]:
            _refund_and_raise(current_user.id, 409, pair["reason"])

        host_elo = invite.elo
        acceptor_elo = user_elo(db, current_user.id)
        same_major = _major_key_of(invite.major or "") == _major_key_of(major)
        unfiltered = not _wanted_of(invite)
        mock = None
        if same_major and unfiltered:
            mock = pool_core.claim_duel_booklet(
                db, invite.host_id, current_user.id, _major_key_of(major), grade=grade)
        if mock is None:
            mock = pool_core.reused_duel(db, invite.host_id, _major_key_of(major),
                grade=grade, plan=pair["plan"], topics=pair.get("topics"))
        if mock is None:
            shared = "، ".join(pair["booklet_subjects"])
            mock = _new_duel_placeholder(
                db, invite.host_id, pair["plan"], invite.major or major, grade,
                f"دوئل زمان‌دار — {shared} — {invite.starts_at.strftime('%Y-%m-%d %H:%M')}")
        match = ArenaMatch(
            student_a_id=invite.host_id,
            student_b_id=current_user.id,
            mock_id=mock.id,
            status="scheduled",
            starts_at=invite.starts_at,
            booked_by=current_user.id,
            elo_a=host_elo,
            elo_b=acceptor_elo,
        )
        db.add(match)
        db.flush()
        invite.accepted_by = current_user.id
        invite.accepted_at = datetime.utcnow()
        invite.match_id = match.id
        db.commit()
        db.refresh(match)
        match_id, mock_id, kickoff = match.id, mock.id, match.starts_at
        booked_host = invite.host_id
        booklet_ready = any((q.get("text") or "").strip()
                            for q in json.loads(mock.questions or "[]"))

    # Live generation for a placeholder booklet, OUTSIDE the lock (the same
    # thread pattern as _reserve_match): plenty of time before kickoff.
    if not booklet_ready:
        threading.Thread(
            target=_generate_duel_booklet, args=(SimpleMatch(match_id, mock_id), pair["plan"]),
            kwargs={"topics": pair["topics"], "grade": grade},
            daemon=True, name=f"arena-scheduled-booklet-{match_id}",
        ).start()
    logger.info("Scheduled match %d booked: host %d vs acceptor %d at %s",
                match_id, booked_host, current_user.id, kickoff)
    return {
        "match_id": match_id,
        "starts_at": kickoff.isoformat(),
        "mock_ready": booklet_ready,
        "your_elo": acceptor_elo,
    }


class SimpleMatch:
    """Minimal match view for the booklet-generation thread (it only reads
    .id and .mock_id of the row it is told about)."""
    def __init__(self, match_id: int, mock_id: int):
        self.id = match_id
        self.mock_id = mock_id


@router.delete("/scheduled/{invite_id}")
def cancel_scheduled(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Host withdraws an open offer; host or acceptor calls off a booked duel
    before kickoff (the invite re-opens when the ACCEPTOR backs out)."""
    with _LOCK:
        invite = db.get(ArenaScheduledInvite, invite_id)
        if not invite:
            raise HTTPException(status_code=404, detail="پیشنهاد پیدا نشد")
        is_host = invite.host_id == current_user.id
        is_acceptor = invite.accepted_by == current_user.id
        if not (is_host or is_acceptor):
            raise HTTPException(status_code=403, detail="این پیشنهاد مال تو نیست")
        # The MATCH row owns the authoritative kickoff (the invite's copy is
        # frozen at booking; trust the match if they ever disagree).
        match = db.get(ArenaMatch, invite.match_id) if invite.match_id else None
        kickoff = (match.starts_at if match and match.starts_at is not None
                   else invite.starts_at)
        if invite.accepted_by is not None and kickoff <= datetime.utcnow():
            raise HTTPException(status_code=409, detail="مسابقه شروع شده؛ دیگر قابل لغو نیست")
        if match and match.status not in ("scheduled",):
            raise HTTPException(status_code=409, detail="مسابقه در جریان است")
        if match:
            match.status = "cancelled"
        if is_acceptor and not is_host:
            # Acceptor backed out: the offer re-opens for someone else.
            invite.accepted_by = None
            invite.accepted_at = None
            invite.match_id = None
        else:
            invite.cancelled_at = datetime.utcnow()
        db.commit()
    return {"cancelled": True}


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
    if match.status == "cancelled":
        raise HTTPException(status_code=409, detail="این مسابقه لغو شده")
    # Scheduled duels must not be played (or scored) before the kickoff.
    if (match.status == "scheduled"
            or (match.starts_at is not None and datetime.utcnow() < match.starts_at)):
        raise HTTPException(status_code=400, detail="مسابقه هنوز شروع نشده")

    mock = db.get(GeneratedMock, match.mock_id) if match.mock_id else None
    if not mock:
        raise HTTPException(status_code=500, detail="دفترچه مسابقه یافت نشد")

    from app.rag import question_bank
    questions = question_bank.active_questions(db, mock)
    if len(questions) != len(json.loads(mock.questions)) and not match.is_ai_opponent:
        # Never compare scores taken against different sets of questions.
        # A report during a live ranked game voids it without moving Elo.
        match.status = "cancelled"
        match.delta_a = match.delta_b = 0
        match.finished_at = datetime.utcnow()
        db.commit()
        raise HTTPException(409, detail="سوالی از این مسابقه گزارش شده است؛ مسابقه بدون تغییر رتبه لغو شد")
    result = _score(questions, payload.answers)
    is_a = match.student_a_id == current_user.id
    if is_a:
        match.score_a = result["percent"]
    else:
        match.score_b = result["percent"]

    # AI-rival matches: score the stored simulated answers through the same
    # _score() and persist both sides - but NEVER touch Elo. This branch is
    # the ranked/exhibition fork; everything below it is ranked-only.
    # (No MockAttempt row for the rival: student_id is NOT NULL and a fake
    # student would pollute attempt analytics - the sampled answers live on
    # match.ai_answers and the rival's scored result in match.score_b.)
    if match.is_ai_opponent:
        try:
            rival_answers = json.loads(match.ai_answers or "{}")
        except (ValueError, TypeError):
            rival_answers = {}
        rival_result = _score(questions, rival_answers)
        match.score_b = rival_result["percent"]
        match.delta_a = 0
        match.delta_b = 0
        match.status = "finished"
        match.finished_at = datetime.utcnow()
        if match.score_a is not None and match.score_b is not None:
            if match.score_a > match.score_b:
                match.winner_id = match.student_a_id or None
            elif match.score_b > match.score_a:
                match.winner_id = None  # the rival "wins" - no user row
        db.commit()
        return {
            **result,
            "finished": True,
            "your_score": result["percent"],
            "opponent_score": match.score_b,
            "ai_rival": match.ai_rival,
            "ranked": False,  # exhibition: no Elo was touched
        }

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
        # Placement K-factor is computed BEFORE the row is marked finished so
        # the current match is not counted in either player's history.
        record_match_rating(match, db)
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
        # AI-rival exhibitions are not part of a player's ranked record.
        .where(ArenaMatch.is_ai_opponent.is_(False))
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
    """Global ranking from User.rating snapshots (O(log n) index query).

    record_match_rating keeps users.rating in sync after every finished
    match, so no ArenaMatch history scan is needed here anymore. Players who
    have never finished a match sit at the 1000 default and sort below any
    rated player with positive delta - same behavior as before for new
    accounts, minus the full-table scan."""
    rows = db.execute(
        select(User.id, User.username, User.rating)
        .where(User.rating != 1000)
        .order_by(User.rating.desc())
        .limit(50)
    ).all()
    out = []
    for i, (sid, username, elo) in enumerate(rows, start=1):
        t = _title(elo)
        out.append({"user_id": sid, "username": username, "elo": elo,
                    "rank": i, "title": t["name"], "color": t["color"],
                    "is_you": sid == current_user.id})
    return out


@router.get("/filters")
def duel_filters(
    major: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The duel filter checkboxes for the caller's own knowledge base.

    Served by the server so the checkbox list can never drift from
    rag/knowledge_base.py, which is also what ENFORCES the ticks during
    matchmaking (a client-side list could not be trusted for that).
    `major` is only a fallback for a client whose profile row is still
    empty - the authoritative major and grade live in the profile.
    """
    resolved, grade = _knowledge_base(db, current_user.id, {"major": major})
    return {**kb.filter_options(resolved), "grade": grade}


@router.get("/{match_id}")
def get_match(
    match_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    with _LOCK:
        _activate_due_matches(db, current_user.id)
        db.commit()
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

    # The booklet's subjects: for a cross-major duel this is the INTERSECTION
    # of both knowledge bases (what the match was fair on), so the UI can
    # show it instead of one player's major.
    subjects: list = []
    book = db.get(GeneratedMock, match.mock_id) if match.mock_id else None
    if (match.status == "pending" and book and match.created_at
            and match.created_at < datetime.utcnow() - timedelta(minutes=15)):
        try:
            ready = any((q.get("text") or "").strip() for q in json.loads(book.questions or "[]"))
        except (ValueError, TypeError):
            ready = False
        if not ready:
            match.status = "cancelled"
            match.generation_error = "ساخت دفترچه مسابقه کامل نشد؛ مسابقه بدون تغییر رتبه لغو شد."
            match.delta_a = match.delta_b = 0
            match.finished_at = datetime.utcnow()
            db.commit()
    if book is not None:
        try:
            for q in json.loads(book.questions or "[]"):
                name = (q.get("subject") or "").strip()
                if name and name not in subjects:
                    subjects.append(name)
        except (ValueError, TypeError):
            pass

    return {
        "match_id": match.id,
        "status": match.status,
        "generation_error": match.generation_error,
        "starts_at": match.starts_at.isoformat() if match.starts_at else None,
        "opponent": opp.username if opp else (_AI_RIVAL_NAME if match.is_ai_opponent else "حریف"),
        "opponent_elo": opp_elo,
        "opponent_delta": opp_delta,
        "your_elo": your_elo,
        "your_delta": your_delta,
        "your_score": your_score,
        "opponent_score": opp_score,
        "won": match.status == "finished" and match.winner_id == current_user.id,
        "mock_id": match.mock_id,
        "is_ai_opponent": match.is_ai_opponent,
        "ranked": not match.is_ai_opponent,
        "subjects": subjects,
        "mock": {
            "duration_minutes": (book.duration_minutes
                                 if book is not None else None),
        } if match.mock_id else None,
    }
