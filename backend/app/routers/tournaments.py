"""Tournament boards and server-scored play for signed-in users."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db, require_admin
from app.tournaments.models import TournamentEvent
from app.tournaments import service

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])


class EventConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=3000)
    major: str = Field(min_length=1, max_length=80)
    grade: str = Field(min_length=1, max_length=40)
    capacity: int = Field(default=32, ge=8, le=64, strict=True)
    league_rounds: int = Field(default=5, ge=1, le=9, strict=True)
    playoff_size: int = Field(default=8, ge=4, le=8, strict=True)
    duration_minutes: int = Field(default=15, ge=1, le=90, strict=True)
    attendance_grace_minutes: int = Field(default=3, ge=1, le=15, strict=True)
    round_interval_hours: int = Field(default=48, ge=1, le=168, strict=True)
    playoff_interval_hours: int = Field(default=24, ge=1, le=168, strict=True)
    starts_at: datetime
    participant_ids: list[StrictInt] = Field(default_factory=list, max_length=64)
    packets: dict[str, list[StrictInt]] = Field(default_factory=dict)

    @field_validator("starts_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("زمان مسابقه باید منطقهٔ زمانی مشخص داشته باشد")
        return value

    @field_validator("title", "major", "grade")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("مقدار خالی مجاز نیست")
        return value.strip()


class Answers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, StrictInt | None] = Field(default_factory=dict, max_length=100)


class DraftAnswers(Answers):
    revision: int = Field(ge=1, strict=True)


class TiebreakConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match_id: str | None = Field(default=None, max_length=100)
    bank_question_ids: list[StrictInt] = Field(min_length=1, max_length=100)
    starts_at: datetime
    duration_minutes: int = Field(default=10, ge=1, le=90, strict=True)

    @field_validator("starts_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("زمان مسابقه باید منطقهٔ زمانی مشخص داشته باشد")
        return value


def _no_store(response):
    # Keep browsers and intermediaries from caching account-specific responses.
    response.headers["Cache-Control"] = "no-store"


@router.get("")
def list_events(response: Response, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _no_store(response)
    items = []
    for event_id in db.scalars(select(TournamentEvent.id).order_by(TournamentEvent.id.desc()).limit(50)):
        state, _ = service.mutate(db, event_id, lambda *_: None)
        items.append(service.public_event(event_id, state, detail=False))
    return {"items": items}


@router.post("/admin/events", status_code=201)
def create_event(body: EventConfig, response: Response, admin=Depends(require_admin), db: Session = Depends(get_db)):
    _no_store(response)
    state = service.build_draft(db, body.model_dump(mode="json"))
    row = TournamentEvent(data=json.dumps(state, ensure_ascii=False), created_by=admin.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return service.public_event(row.id, state)


@router.patch("/admin/events/{event_id:int}")
def edit_event(event_id: int, body: EventConfig, response: Response, admin=Depends(require_admin), db: Session = Depends(get_db)):
    _no_store(response)

    def change(state, now):
        if state["status"] != "draft":
            service.fail("پس از آغاز، تغییر فهرست، برنامه یا سؤال‌های تورنومنت مجاز نیست.")
        new_state = service.build_draft(db, body.model_dump(mode="json"))
        state.clear()
        state.update(new_state)

    state, _ = service.mutate(db, event_id, change)
    return service.public_event(event_id, state)


@router.post("/admin/events/{event_id:int}/activate")
def activate_event(event_id: int, response: Response, admin=Depends(require_admin), db: Session = Depends(get_db)):
    _no_store(response)
    state, _ = service.mutate(db, event_id, lambda state, now: service.activate(state, db, now))
    return service.public_event(event_id, state)


@router.post("/admin/events/{event_id:int}/advance")
def advance_event(event_id: int, response: Response, admin=Depends(require_admin), db: Session = Depends(get_db)):
    _no_store(response)
    state, _ = service.mutate(db, event_id, lambda *_: None)
    return service.public_event(event_id, state)


@router.post("/admin/events/{event_id:int}/tiebreak")
def prepare_tiebreak(event_id: int, body: TiebreakConfig, response: Response, admin=Depends(require_admin), db: Session = Depends(get_db)):
    _no_store(response)
    state, _ = service.mutate(db, event_id, lambda state, now: service.prepare_tiebreak(db, state, body.model_dump(mode="json"), now))
    return service.public_event(event_id, state)


@router.get("/{event_id:int}")
def event_detail(event_id: int, response: Response, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _no_store(response)
    state, _ = service.mutate(db, event_id, lambda *_: None)
    return service.public_event(event_id, state)


@router.get("/{event_id:int}/me")
def personal_schedule(event_id: int, response: Response, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _no_store(response)
    state, _ = service.mutate(db, event_id, lambda *_: None)
    return service.my_matches(event_id, state, user.id)


@router.post("/{event_id:int}/matches/{match_id}/start")
def start_game(event_id: int, match_id: str, response: Response, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _no_store(response)
    _, result = service.mutate(db, event_id, lambda state, now: service.start_match(state, now, event_id, match_id, user.id))
    return result


@router.post("/{event_id:int}/matches/{match_id}/submit")
def submit_game(event_id: int, match_id: str, body: Answers, response: Response, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _no_store(response)
    _, result = service.mutate(db, event_id, lambda state, now: service.submit_match(state, now, match_id, user.id, body.answers))
    return result


@router.put("/{event_id:int}/matches/{match_id}/answers")
def save_game_answers(event_id: int, match_id: str, body: DraftAnswers, response: Response, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _no_store(response)
    _, result = service.mutate(db, event_id, lambda state, now: service.save_answers(state, now, match_id, user.id, body.answers, body.revision))
    return result
