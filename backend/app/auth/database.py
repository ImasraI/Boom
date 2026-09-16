from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
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
    # Unique index for phone (SQLite allows multiple NULLs).
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)"
            )
        )


ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
