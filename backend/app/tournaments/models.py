"""Additive tournament storage, registered on the application's existing Base."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text

from app.auth.database import Base


class TournamentEvent(Base):
    __tablename__ = "tournament_events"

    id = Column(Integer, primary_key=True)
    # Packets, roster and attempts share one revision so starting/submitting a
    # match and advancing its round can be committed atomically with CAS.
    data = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
