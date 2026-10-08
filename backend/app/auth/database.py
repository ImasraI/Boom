from datetime import date, datetime
from pathlib import Path
import os
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, sessionmaker, relationship


# Keep the SQLite file next to the backend package root, regardless of CWD.
_DB_PATH = Path(__file__).resolve().parents[2] / "rag_data.db"
DATABASE_URL = os.environ.get("BOOM_DATABASE_URL") or f"sqlite:///{_DB_PATH.as_posix()}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    phone_verified = Column(Boolean, default=False, nullable=False, server_default="0")
    # Admin flag: gates /api/admin/* (require_admin dependency). Only set
    # through scripts/manage_admin.py - never through any HTTP endpoint.
    is_admin = Column(Boolean, default=False, nullable=False, server_default="0")
    # Arena Elo snapshot, maintained by record_match_rating so the
    # leaderboard can query/sort on users directly instead of scanning every
    # finished ArenaMatch on each request. 1000 = unrated starting rating.
    rating = Column(Integer, nullable=False, default=1000, server_default="1000")
    created_at = Column(DateTime, default=datetime.utcnow)


class PhoneCode(Base):
    """One SMS verification code sent to a phone number.

    Signed-up users keep their user row when re-verifying; signups only
    materialize a user row at /register/complete (after code verification).
    """

    __tablename__ = "phone_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, index=True, nullable=False)  # normalized 9xxxxxxxxx
    code_hash = Column(String, nullable=False)          # sha256(code + SECRET_KEY)
    purpose = Column(String, nullable=False, default="signup")
    attempts = Column(Integer, nullable=False, default=0)
    consumed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class SignupAllowlist(Base):
    """Phone numbers allowed to sign up with the bypass passcode.

    Stopgap for the SMS-template-approval limbo: until SMS.ir approves the
    verification template, numbers on this list can complete signup using
    the shared bypass code (SIGNUP_BYPASS_CODE, default 111111) instead of
    a texted code. Managed only through the admin panel/CLI.
    """

    __tablename__ = "signup_allowlist"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)  # 9xxxxxxxxx
    note = Column(String, nullable=True)  # who/why, for the admin's own bookkeeping
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyTask(Base):
    __tablename__ = "daily_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # study, test, review, practice
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    # --- Replanning / backlog fields (growth-readiness project 3) ---
    # planned | completed | partially_completed | missed | skipped_by_student
    # | cancelled_by_planner | rescheduled
    status: Mapped[Optional[str]] = mapped_column(String, default="planned")
    actual_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completed_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    planned_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)      # why it was not done
    replan_note: Mapped[Optional[str]] = mapped_column(String, nullable=True) # planner-facing decision note
    miss_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)     # consecutive misses of this task


class BookCatalog(Base):
    __tablename__ = "book_catalog"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(String, unique=True, index=True, nullable=False)
    subject = Column(String, nullable=False)
    chapter = Column(String, nullable=True)
    section = Column(String, nullable=True)
    question_range_start = Column(Integer, nullable=True)
    question_range_end = Column(Integer, nullable=True)
    difficulty_tier = Column(String, nullable=True)  # easy, medium, hard
    avg_seconds_per_question = Column(Integer, nullable=True)


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    topics = relationship("Topic", back_populates="subject")
    resources = relationship("Resource", back_populates="subject")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    name = Column(String, nullable=False)
    parent_topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    prerequisite_topic_ids = Column(String, nullable=True)  # comma-separated IDs
    mastery = Column(String, nullable=True)  # percentage or level
    priority = Column(Integer, nullable=True)  # 1-5
    subject = relationship("Subject", back_populates="topics")
    resources = relationship("Resource", back_populates="topic")


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # book, chapter, lesson, question_set
    title = Column(String, nullable=False)
    topic_ids = Column(String, nullable=True)  # comma-separated topic IDs
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)
    sections = Column(String, nullable=True)  # comma-separated section names
    subject = relationship("Subject", back_populates="resources")
    topic = relationship("Topic", back_populates="resources")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=True)
    type = Column(String, nullable=False)  # study, test, review, practice
    duration_minutes = Column(Integer, nullable=False)
    scheduled_for = Column(Date, nullable=False)
    priority = Column(Integer, nullable=True)  # 1-5
    status = Column(String, nullable=False)  # pending, in_progress, completed, completed_late


class StudySession(Base):
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    completion_data = Column(Text, nullable=True)  # JSON string
    # ---- Growth-readiness project 4: REAL session logging ----
    # Distinguishes "what was planned" from "what actually happened" so the
    # planner can build per-student estimates. Optional columns - daily
    # logging must stay fast (three-tap quick log).
    plan_item_id = Column(Integer, nullable=True)  # future plan_items FK
    subject_name = Column(String, nullable=True)  # free label when no Subject row
    topic_name = Column(String, nullable=True)
    actual_minutes = Column(Integer, nullable=True)
    attempted_questions = Column(Integer, nullable=True)
    correct_count = Column(Integer, nullable=True)
    wrong_count = Column(Integer, nullable=True)
    blank_count = Column(Integer, nullable=True)
    perceived_difficulty = Column(Integer, nullable=True)  # 1-5
    focus_level = Column(Integer, nullable=True)  # 1-5
    energy_level = Column(Integer, nullable=True)  # 1-5
    interruption_count = Column(Integer, nullable=True)
    # planned | in_progress | completed | partially_completed | missed |
    # skipped_by_student | cancelled_by_planner | rescheduled
    completion_status = Column(String, nullable=True)
    logged_via = Column(String, nullable=True)  # timer | quick | auto_test
    created_at = Column(DateTime, default=datetime.utcnow)


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    source = Column(String, nullable=True)  # mock_exam, konkoor, etc.
    results = Column(Text, nullable=True)  # JSON string with scores per topic


class WrongAnswer(Base):
    """One question the student got wrong (or skipped) on any test.

    The planner reads these to weight weak subjects/topics when building
    the weekly plan and when picking exact question ranges to schedule.
    """

    __tablename__ = "wrong_answers"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String, nullable=False, index=True)  # فیزیک، شیمی، ...
    topic = Column(String, nullable=True)  # مبحث، e.g. حرکت‌شناسی
    book = Column(String, nullable=True)  # source book filename, if known
    page = Column(Integer, nullable=True)  # page in the book, if known
    question_text = Column(Text, nullable=True)  # question stem for review
    correct_answer = Column(String, nullable=True)  # الف/ب/ج/د or free text
    student_answer = Column(String, nullable=True)
    was_blank = Column(Boolean, default=False)  # skipped vs answered wrong
    source = Column(String, nullable=True)  # mock / arena / practice / ocr
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewLog(Base):
    """A completed spaced-review event for one subject/topic."""

    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String, nullable=False, index=True)
    topic = Column(String, nullable=False)
    rating = Column(Integer, nullable=True)  # 1..5 self-rating after review
    created_at = Column(DateTime, default=datetime.utcnow)


class GeneratedMock(Base):
    """An AI-generated konkur-standard mock exam (booklet + answer key)."""

    __tablename__ = "generated_mocks"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    major = Column(String, nullable=True)  # ریاضی فیزیک / تجربی
    grade = Column(String, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=120)
    questions = Column(Text, nullable=False)  # JSON: [{id, subject, topic, text, options, answer, explanation, page, book}]
    # "pending_use" = unassigned pool row awaiting a student; "claimed" =
    # owned by student_id (live-generated, duel, or claimed pool row).
    status = Column(String, nullable=False, default="claimed",
                    server_default="claimed")
    difficulty = Column(String, nullable=False, default="", server_default="")
    bank_scope = Column(String, nullable=False, default="private", server_default="private")
    bank_indexed = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)


class BankQuestion(Base):
    """An independent question; booklet snapshots refer to its stable id."""
    __tablename__ = "bank_questions"
    id = Column(Integer, primary_key=True)
    fingerprint = Column(String, unique=True, nullable=False, index=True)
    owner_id = Column(Integer, nullable=False, default=0, index=True)
    major = Column(String, nullable=False, default="", index=True)
    grade = Column(String, nullable=False, default="")
    grade_level = Column(Integer, nullable=False, default=12, index=True)
    difficulty = Column(String, nullable=False, default="konkur", index=True)
    subject = Column(String, nullable=False, index=True)
    topic = Column(String, nullable=False, default="")
    content = Column(Text, nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="active", index=True)
    uses = Column(Integer, nullable=False, default=0)
    admin_note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class QuestionReport(Base):
    __tablename__ = "question_reports"
    __table_args__ = (UniqueConstraint("question_id", "student_id", "mock_id", name="uq_question_report_user_mock"),)
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("bank_questions.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mock_id = Column(Integer, ForeignKey("generated_mocks.id"), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MockAttempt(Base):
    """One student's run through a generated mock, with per-question answers."""

    __tablename__ = "mock_attempts"

    id = Column(Integer, primary_key=True, index=True)
    mock_id = Column(Integer, ForeignKey("generated_mocks.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    answers = Column(Text, nullable=True)  # JSON: {question_id: "0".."3" or ""}
    duration_seconds = Column(Integer, nullable=True)
    score = Column(Float, nullable=True)  # konkur percent after negative marking
    correct = Column(Integer, nullable=True)
    wrong = Column(Integer, nullable=True)
    blank = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ArenaQueueEntry(Base):
    """A student waiting in the ranked matchmaking queue."""

    __tablename__ = "arena_queue"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    elo = Column(Integer, nullable=False, default=1000)
    joined_at = Column(DateTime, default=datetime.utcnow)
    # ---- knowledge base (see rag/knowledge_base.py) ----
    # A duel booklet is generated from the INTERSECTION of both players'
    # subjects, so each queued entry must carry its own major and grade:
    # matchmaking never pairs two students whose exam material does not
    # overlap (a زبان‌های خارجی student shares no booklet subject with the
    # other majors, for example).
    major = Column(String, nullable=True)
    grade = Column(String, nullable=True)
    # JSON list of study subjects the player wants to be tested on. Every
    # entry is a MATCHMAKING requirement: the opponent must study all of
    # them (empty/None = no filter).
    wanted = Column(Text, nullable=True)  # JSON string


class ArenaMatch(Base):
    """A ranked duel between two students on an AI-generated mock."""

    __tablename__ = "arena_matches"

    id = Column(Integer, primary_key=True, index=True)
    student_a_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_b_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mock_id = Column(Integer, ForeignKey("generated_mocks.id"), nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending / finished
    elo_a = Column(Integer, nullable=False, default=1000)
    elo_b = Column(Integer, nullable=False, default=1000)
    score_a = Column(Float, nullable=True)  # konkur percent after negative marking
    score_b = Column(Float, nullable=True)
    delta_a = Column(Integer, nullable=True)  # elo change for A
    delta_b = Column(Integer, nullable=True)
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    generation_error = Column(Text, nullable=True)
    # ---- AI-rival exhibition matches (is_ai_opponent=True) ----
    # A SEPARATE, non-ranked track: these rows NEVER feed record_match_rating
    # (guarded), the placement K count, user_elo, /me or the public
    # leaderboard - see the exclusion points in this module and arena.submit.
    # The "opponent" is simulated: student_b_id uses the 0 sentinel (see
    # pool_core.POOL_OWNER_ID) and its sampled
    # per-question answers live in ai_answers so scoring runs identically.
    is_ai_opponent = Column(Boolean, nullable=False, default=False,
                            server_default="0")
    # Key into arena._AI_RIVAL_LEVELS (named difficulty, not raw probability).
    ai_rival = Column(String, nullable=True)
    # JSON {question_id: chosen option index} sampled at the level's accuracy.
    ai_answers = Column(Text, nullable=True)
    # ---- scheduled matches (arena scheduling option) ----
    # UTC kickoff. Null for the classic instant modes (matchmaking, AI rival);
    # set for a scheduled duel, which is created with status="scheduled"
    # and lazily flips to "pending" when starts_at arrives (both players
    # then see it through the normal /status + /{id} polling).
    starts_at = Column(DateTime, nullable=True)
    # Who BOOKED the match (the acceptor becomes student_b). Kept for the
    # cancel-authorization rule: only the host or the acceptor may cancel.
    # For instant modes this is Null (= not a scheduled match).
    booked_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class ArenaScheduledInvite(Base):
    """An OPEN offer: "I want a duel at <time>, who's in?"

    The queue of a matchable opponent sits in a public list so anyone can
    accept it before kickoff; once accepted, the row freezes and a real
    ArenaMatch with status="scheduled" is created for both players. The
    booklet is claimed from the duel pool AT ACCEPT TIME so it is ready
    before the match starts (no LLM wait at kickoff).
    """

    __tablename__ = "arena_scheduled_invites"

    id = Column(Integer, primary_key=True, index=True)
    host_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # UTC kickoff the match becomes playable for BOTH players.
    starts_at = Column(DateTime, nullable=False, index=True)
    # Constraints the acceptor must satisfy (same rules as live matchmaking:
    # same booklet material + rating band, so a scheduled duel is as fair as
    # an instant one). Empty wanted = no subject filter.
    major = Column(String, nullable=True)
    grade = Column(String, nullable=True)
    elo = Column(Integer, nullable=False, default=1000)
    wanted = Column(Text, nullable=True)  # JSON list (host's subject ticks)
    # Null until someone books the slot.
    accepted_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    accepted_at = Column(DateTime, nullable=True)
    # The ArenaMatch created on acceptance (acceptor = student_b).
    match_id = Column(Integer, ForeignKey("arena_matches.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Host gave up waiting (or the acceptor backed out). Cancelled rows stay
    # visible to the two parties until kickoff, then disappear from the list.
    cancelled_at = Column(DateTime, nullable=True)


class StudentProfile(Base):
    """Server-side source of truth for the student's onboarding profile.

    Growth-readiness project 1: the same plan/profile must appear on every
    device, and clearing browser storage must not lose data. The frontend
    keeps localStorage as an offline CACHE; this row is authoritative.
    `version` + `updated_at` make concurrent edits detectable (PATCH sends
    the version it based on; a stale version gets 409 + server state back
    instead of a silent overwrite).
    """

    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False,
                     unique=True, index=True)
    name = Column(String, nullable=True)
    major = Column(String, nullable=True)
    grade = Column(String, nullable=True)
    exam_year = Column(String, nullable=True)
    target_rank = Column(String, nullable=True)
    study_hours = Column(String, nullable=True)
    # JSON list of mock-exam providers the student takes.
    test_exams = Column(Text, nullable=True)  # JSON string
    # Daily availability JSON: {"wake": "06:30", "sleep": "23:00",
    #  "daily_hours": {"0": 4, ...}} - planner input, server-owned.
    availability = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)


class StudentCalendar(Base):
    """Account-owned calendar, with a version to reject stale device writes."""
    __tablename__ = "student_calendars"
    student_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    weeks = Column(Text, nullable=False, default="{}")
    statics = Column(Text, nullable=False, default="[]")
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Homework(Base):
    """Student-reviewed homework; drafts never become calendar activities."""
    __tablename__ = "homework"
    id = Column(String, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String, nullable=False)
    details = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskProgress(Base):
    """One latest outcome per student and calendar task; retries replace, not duplicate."""
    __tablename__ = "task_progress"
    student_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    client_ref = Column(String, primary_key=True)
    source_ref = Column(String, nullable=True)
    resource = Column(String, nullable=True)
    question_start = Column(Integer, nullable=True)
    question_end = Column(Integer, nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    date = Column(Date, nullable=False)
    subject = Column(String, nullable=False)
    topic = Column(String, nullable=False, default="")
    task_type = Column(String, nullable=False, default="study")
    planned_minutes = Column(Integer, nullable=False)
    actual_minutes = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChallengeInvite(Base):
    """Asynchronous friend challenge on an already-played mock.

    Unlike ArenaMatch (matchmaking, both players online simultaneously, Elo
    at stake), a challenge is a shareable link: the sender challenges friends
    with a booklet they have already attempted themselves, the recipient
    plays it whenever they are free through the normal /api/mocks flow, and
    both stored scores are compared once the recipient is done.
    """

    __tablename__ = "challenge_invites"

    id = Column(Integer, primary_key=True, index=True)
    mock_id = Column(Integer, ForeignKey("generated_mocks.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Short unambiguous code embedded in the shareable link (unique).
    invite_code = Column(String, unique=True, index=True, nullable=False)
    # Null until someone claims the invite by accepting it.
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String, nullable=False, default="pending")  # pending / accepted / completed
    created_at = Column(DateTime, default=datetime.utcnow)
    # Stale invites die silently: expired pending invites can no longer be
    # accepted (checked lazily - no cleanup job needed).
    expires_at = Column(DateTime, nullable=False)


def _ensure_column(table: str, column: str, ddl_type: str) -> None:
    """Add a missing column to an existing SQLite table (create_all won't)."""
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return
    existing = {col["name"] for col in insp.get_columns(table)}
    if column in existing:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def ensure_schema() -> None:
    """Create missing tables and backfill columns added after initial create_all."""
    Base.metadata.create_all(bind=engine)
    _ensure_column("task_progress", "source_ref", "VARCHAR")
    _ensure_column("task_progress", "resource", "VARCHAR")
    for column in ("question_start", "question_end", "page_start", "page_end"):
        _ensure_column("task_progress", column, "INTEGER")
    # users.phone was added after the first schema create; migrate existing DBs.
    _ensure_column("users", "phone", "VARCHAR")
    _ensure_column("users", "phone_verified", "BOOLEAN DEFAULT 0")
    _ensure_column("users", "is_admin", "BOOLEAN DEFAULT 0")
    _ensure_column("daily_tasks", "status", "VARCHAR DEFAULT 'planned'")
    _ensure_column("daily_tasks", "actual_minutes", "INTEGER")
    _ensure_column("daily_tasks", "completed_count", "INTEGER")
    _ensure_column("daily_tasks", "planned_count", "INTEGER")
    _ensure_column("daily_tasks", "reason", "VARCHAR")
    _ensure_column("daily_tasks", "replan_note", "VARCHAR")
    _ensure_column("daily_tasks", "miss_count", "INTEGER DEFAULT 0")
    # Mock pool: "pending_use" rows sit unassigned in the pre-generated pool;
    # "claimed" rows belong to the student in student_id. Legacy rows (and
    # arena duel rows) predate the pool and default to "claimed".
    _ensure_column("generated_mocks", "status", "VARCHAR DEFAULT 'claimed'")
    # Difficulty the booklet was generated for - pool rows are matched to
    # requests by (major, difficulty), so it must be persisted.
    _ensure_column("generated_mocks", "difficulty", "VARCHAR DEFAULT ''")
    _ensure_column("generated_mocks", "bank_scope", "VARCHAR DEFAULT 'private'")
    _ensure_column("generated_mocks", "bank_indexed", "BOOLEAN DEFAULT 0")
    # Arena Elo snapshot on the user (see record_match_rating); existing DBs
    # backfill at the unrated starting value.
    _ensure_column("users", "rating", "INTEGER DEFAULT 1000")
    # AI-rival exhibition columns on arena_matches (existing DBs backfill;
    # is_ai_opponent defaults to 0 = a real ranked match).
    _ensure_column("arena_matches", "is_ai_opponent", "BOOLEAN DEFAULT 0")
    # Scheduled duels (arena scheduling option): kickoff timestamp + who
    # booked the match. Null on every classic row.
    _ensure_column("arena_matches", "starts_at", "TIMESTAMP")
    _ensure_column("arena_matches", "generation_error", "TEXT")
    _ensure_column("arena_matches", "booked_by", "INTEGER")
    _ensure_column("arena_matches", "ai_rival", "VARCHAR")
    _ensure_column("arena_matches", "ai_answers", "TEXT")
    # Arena knowledge-base matchmaking: the queue entry remembers the
    # player's major, grade and ticked subjects (existing DBs backfill as
    # NULL -> no filter, and matchmaking then falls back to the profile row).
    _ensure_column("arena_queue", "major", "VARCHAR")
    _ensure_column("arena_queue", "grade", "VARCHAR")
    _ensure_column("arena_queue", "wanted", "TEXT")
    # Growth-readiness project 4: real study-session logging columns
    # (existing DBs get the new columns; new tables create them directly).
    _ensure_column("study_sessions", "plan_item_id", "INTEGER")
    _ensure_column("study_sessions", "subject_name", "VARCHAR")
    _ensure_column("study_sessions", "topic_name", "VARCHAR")
    _ensure_column("study_sessions", "actual_minutes", "INTEGER")
    _ensure_column("study_sessions", "attempted_questions", "INTEGER")
    _ensure_column("study_sessions", "correct_count", "INTEGER")
    _ensure_column("study_sessions", "wrong_count", "INTEGER")
    _ensure_column("study_sessions", "blank_count", "INTEGER")
    _ensure_column("study_sessions", "perceived_difficulty", "INTEGER")
    _ensure_column("study_sessions", "focus_level", "INTEGER")
    _ensure_column("study_sessions", "energy_level", "INTEGER")
    _ensure_column("study_sessions", "interruption_count", "INTEGER")
    _ensure_column("study_sessions", "completion_status", "VARCHAR")
    _ensure_column("study_sessions", "logged_via", "VARCHAR")
    _ensure_column("study_sessions", "created_at", "TIMESTAMP")
    # Unique index for phone (SQLite allows multiple NULLs).
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)"
            )
        )


def user_elo(db, student_id: int) -> int:
    """Current Elo for a student: the latest Elo snapshot across their real
    (non-AI-rival) arena matches, or the 1000 starting rating when they have
    never played.

    AI-rival exhibition rows are EXCLUDED: they store an elo_a snapshot taken
    at match creation, so letting them win "latest row" could resurrect a
    stale rating (e.g. a pending real match finishing after the AI row was
    created). Only real matches ever move the rating.
    """
    from sqlalchemy import select

    row = latest_arena_match(db, student_id)
    if row is None:
        return 1000
    if row.student_a_id == student_id:
        return int(row.elo_a or 1000)
    return int(row.elo_b or 1000)


def latest_arena_match(db, student_id: int):
    """The player's most recent REAL (non-AI-rival) arena match row.

    user_elo() reads the Elo snapshot off this row. Scheduled matches that
    have not started yet (status="scheduled") must NOT answer this query:
    their elo_a/elo_b are ratings frozen at booking time, and if a player
    plays a normal ranked duel after booking one, the older rating would
    shadow the fresh one. Weakest link: exclude every non-finished row.
    """
    return db.execute(
        select(ArenaMatch)
        .where((ArenaMatch.student_a_id == student_id)
               | (ArenaMatch.student_b_id == student_id))
        .where(ArenaMatch.is_ai_opponent.is_(False))
        .where(ArenaMatch.status == "finished")
        .order_by(ArenaMatch.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def record_match_rating(match: ArenaMatch, db=None) -> None:
    """Compute Elo deltas for a finished arena match using standard Elo over
    konkur-percentage scores, and persist them on the row + User.rating.

    Each player's expected score comes from the rating gap; the actual score
    is the normalized konkur percentage (0..1), so blowing out a weak opponent
    on an easy mock still caps the gain. K is 48 for each player's first 10
    finished matches (placement acceleration) and 32 afterwards. Call once,
    after both scores exist and BEFORE the caller commits `match.status =
    "finished"` (the placement count must not include the current match).

    `db`: the caller's session when available (the arena submit endpoint
    passes it) so the User.rating snapshots commit atomically with the match.
    Falls back to a short-lived SessionLocal for direct/test callers.

    AI-RIVAL EXCLUSION (airtight): matches with is_ai_opponent=True return
    immediately with zero deltas - no Elo math, no User.rating writes. The
    arena submit endpoint additionally skips calling this for such matches;
    the guard makes the exclusion hold even if a future caller forgets.
    """
    if getattr(match, "is_ai_opponent", False):
        # Exhibition vs the simulated rival: zero deltas, ratings untouched.
        match.delta_a = 0
        match.delta_b = 0
        return
    session = db if db is not None else SessionLocal()
    own_session = db is None
    try:
        def _k_for(student_id) -> float:
            if not student_id:
                return 32.0
            played = session.execute(
                select(func.count()).select_from(ArenaMatch).where(
                    ArenaMatch.status == "finished",
                    # AI-rival exhibitions never consume placement
                    # acceleration - only real matches count toward the 10.
                    ArenaMatch.is_ai_opponent.is_(False),
                    (ArenaMatch.student_a_id == student_id)
                    | (ArenaMatch.student_b_id == student_id),
                )
            ).scalar() or 0
            return 48.0 if played < 10 else 32.0

        ka = _k_for(match.student_a_id)
        kb = _k_for(match.student_b_id)
        ea = 1.0 / (1.0 + 10 ** ((float(match.elo_b or 1000) - float(match.elo_a or 1000)) / 400.0))
        sa = max(0.0, min(1.0, float(match.score_a or 0.0) / 100.0))
        sb = max(0.0, min(1.0, float(match.score_b or 0.0) / 100.0))
        # Normalize so the two actual scores sum to 1 (like a two-player game).
        total = sa + sb
        if total <= 0:
            sa_n, sb_n = 0.5, 0.5
        else:
            sa_n, sb_n = sa / total, sb / total
        match.delta_a = int(round(ka * (sa_n - ea)))
        match.delta_b = int(round(kb * (sb_n - (1.0 - ea))))
        match.elo_a = int(match.elo_a or 1000) + match.delta_a
        match.elo_b = int(match.elo_b or 1000) + match.delta_b
        # Persist snapshots onto the users so the leaderboard never needs to
        # rescan ArenaMatch history.
        for sid, elo in ((match.student_a_id, match.elo_a),
                         (match.student_b_id, match.elo_b)):
            if sid:
                u = session.get(User, sid)
                if u is not None:
                    u.rating = int(elo)
        if own_session:
            session.commit()
    finally:
        if own_session:
            session.close()


ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
