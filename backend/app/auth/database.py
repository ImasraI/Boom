from datetime import datetime
from pathlib import Path

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
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, sessionmaker, relationship


# Keep the SQLite file next to the backend package root, regardless of CWD.
_DB_PATH = Path(__file__).resolve().parents[2] / "rag_data.db"
DATABASE_URL = f"sqlite:///{_DB_PATH.as_posix()}"
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


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyTask(Base):
    __tablename__ = "daily_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    subject = Column(String, nullable=False)
    task_type = Column(String, nullable=False)  # study, test, review, practice
    description = Column(Text, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    completed = Column(Boolean, default=False)


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
    # users.phone was added after the first schema create; migrate existing DBs.
    _ensure_column("users", "phone", "VARCHAR")
    _ensure_column("users", "phone_verified", "BOOLEAN DEFAULT 0")
    # Unique index for phone (SQLite allows multiple NULLs).
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)"
            )
        )


def user_elo(db, student_id: int) -> int:
    """Current Elo for a student: the latest Elo snapshot across their arena
    matches, or the 1000 starting rating when they have never played."""
    from sqlalchemy import select

    row = db.execute(
        select(ArenaMatch)
        .where(
            (ArenaMatch.student_a_id == student_id)
            | (ArenaMatch.student_b_id == student_id)
        )
        .order_by(ArenaMatch.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return 1000
    if row.student_a_id == student_id:
        return int(row.elo_a or 1000)
    return int(row.elo_b or 1000)


def record_match_rating(match: ArenaMatch) -> None:
    """Compute Elo deltas for a finished arena match using standard Elo with
    K=32 over konkur-percentage scores, and persist them on the row.

    Each player's expected score comes from the rating gap; the actual score
    is the normalized konkur percentage (0..1), so blowing out a weak opponent
    on an easy mock still caps the gain. Call once, after both scores exist.
    """
    K = 32.0
    ea = 1.0 / (1.0 + 10 ** ((float(match.elo_b or 1000) - float(match.elo_a or 1000)) / 400.0))
    sa = max(0.0, min(1.0, float(match.score_a or 0.0) / 100.0))
    sb = max(0.0, min(1.0, float(match.score_b or 0.0) / 100.0))
    # Normalize so the two actual scores sum to 1 (like a two-player game).
    total = sa + sb
    if total <= 0:
        sa_n, sb_n = 0.5, 0.5
    else:
        sa_n, sb_n = sa / total, sb / total
    match.delta_a = int(round(K * (sa_n - ea)))
    match.delta_b = int(round(K * (sb_n - (1.0 - ea))))
    match.elo_a = int(match.elo_a or 1000) + match.delta_a
    match.elo_b = int(match.elo_b or 1000) + match.delta_b


ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
