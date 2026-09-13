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
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, sessionmaker


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
