"""Pool generation tests: acceptance rules, provider outage handling, counts.

Regression context: the pool produced ZERO booklets for minutes on end. Two
independent causes:

  1. ``build_pool_booklet`` rejected the whole booklet unless every subject's
     verified question count *exactly* equalled the plan (105 questions for
     ریاضی فیزیک). The generator and the verifier both legitimately drop
     questions, so that gate could never pass and every multi-minute booklet
     was thrown away.
  2. A provider refusing calls (HTTP 429 daily-quota exhaustion) was retried
     with backoff for every subject of every shelf, so the sweep looked hung
     while the panel said "0 booklets" and gave no reason.

These tests lock in the fixes: a materially complete booklet is kept (with an
honest duration), an unusable one is dropped, a refused call aborts fast with
the reason recorded, and question counts are reported as they happen.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import httpx

from app.auth.database import Base, get_db
from app.auth.deps import require_admin
from app.rag import mock_generation as mg
from app.rag import pool_core
from app.rag.llm import _quota_reason
from app.routers import admin


@pytest.fixture(autouse=True)
def _clean_pool_state():
    pool_core.clear_cancel()
    pool_core.begin_progress("test")
    pool_core.finish_progress()
    yield
    pool_core.clear_cancel()
    pool_core.begin_progress("test")
    pool_core.finish_progress()


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _fake_questions(plan, fill=1.0, skip=()):
    """`fill` of every planned subject, already marked verified."""
    out = []
    for row in plan:
        if row["name"] in skip:
            continue
        for i in range(int(row["questions"] * fill)):
            out.append({
                "subject": row["name"], "topic": "مبحث", "text": f"سوال {i}",
                "options": ["a", "b", "c", "d"], "answer": i % 4,
                "explanation": "توضیح", "verification_status": "verified",
            })
    return out


def _patch_booklet(monkeypatch, questions):
    """Stub the generator + verifier so only build_pool_booklet's own rules
    are under test."""
    monkeypatch.setattr(mg, "generate_booklet",
                        lambda *a, **k: [dict(q) for q in questions])
    monkeypatch.setattr(
        mg, "verify_and_repair_booklet",
        lambda qs, *a, **k: [{**q, "verification_status": "verified"} for q in qs])


def test_short_but_complete_booklet_is_kept_with_a_scaled_duration(monkeypatch):
    """A paper at 60% of the official plan is servable - it must NOT be
    thrown away (the old exact-match rule rejected everything)."""
    plan = mg.default_plan("riazi")
    questions = _fake_questions(plan, fill=0.6)
    _patch_booklet(monkeypatch, questions)

    kept, kept_plan, duration = mg.build_pool_booklet("riazi", "easy",
                                                      user_id=0)

    planned_total = sum(r["questions"] for r in plan)
    full_duration = sum(r["minutes"] for r in plan)
    assert len(kept) == len(questions)
    assert len(kept_plan) == len(plan)
    # Never advertise more time than the questions the paper actually holds.
    assert duration == max(1, round(full_duration * len(kept) / planned_total))
    assert duration < full_duration


def test_booklet_below_the_fill_floor_is_discarded(monkeypatch):
    plan = mg.default_plan("riazi")
    _patch_booklet(monkeypatch, _fake_questions(plan, fill=0.3))
    kept, _plan, _duration = mg.build_pool_booklet("riazi", "easy", user_id=0)
    assert kept == []


def test_booklet_missing_a_subject_is_discarded(monkeypatch):
    """Filling the total but losing a whole subject would serve a paper with
    a missing section as a full mock."""
    plan = mg.default_plan("riazi")
    victim = plan[-1]["name"]
    _patch_booklet(monkeypatch, _fake_questions(plan, fill=1.0, skip=(victim,)))
    kept, _plan, _duration = mg.build_pool_booklet("riazi", "easy", user_id=0)
    assert kept == []


def test_full_booklet_keeps_its_duration(monkeypatch):
    plan = mg.default_plan("riazi")
    _patch_booklet(monkeypatch, _fake_questions(plan, fill=1.0))
    kept, _plan, duration = mg.build_pool_booklet("riazi", "easy", user_id=0)
    assert len(kept) == sum(r["questions"] for r in plan)
    assert duration == sum(r["minutes"] for r in plan)


def test_provider_refusal_stops_immediately_and_reports_the_reason(monkeypatch):
    """An empty response is the provider refusing, not a bad model answer:
    retrying with half the questions only doubles the wasted quota."""
    calls = []
    events = []

    class RefusingClient:
        last_error = "HTTP 429 (quota exceeded | GenerateRequestsPerDayPerProjectPerModel-FreeTier)"

        def generate(self, messages, max_tokens=None, timeout=None):
            calls.append(messages)
            return ""

    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: RefusingClient())
    monkeypatch.setattr(mg, "retrieve_book_context", lambda *a, **k: "context")
    monkeypatch.setattr(mg, "build_booklet_prompt", lambda *a, **k: "prompt")

    rows = mg._generate_subject_questions(
        user_id=1, row={"name": "ریاضی", "questions": 10, "minutes": 30},
        topics=[], difficulty="easy", max_tokens=500, timeout=5,
        report=lambda event, data: events.append((event, data)),
    )

    assert rows == []
    assert len(calls) == 1  # no half-count retry on a refused call
    provider_events = [d for e, d in events if e == "provider_error"]
    assert provider_events and "GenerateRequestsPerDay" in provider_events[0]["message"]


def test_generate_booklet_reports_question_counts(monkeypatch):
    payload = ('{"questions":[{"subject":"ریاضی","topic":"حد","text":"سوال یک",'
               '"options":["1","2","3","4"],"answer":2,"explanation":"چون"}]}')

    class WorkingClient:
        last_error = ""

        def generate(self, messages, max_tokens=None, timeout=None):
            return payload

    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: WorkingClient())
    monkeypatch.setattr(mg, "retrieve_book_context", lambda *a, **k: "context")
    events = []

    rows = mg.generate_booklet(1, [{"name": "ریاضی", "questions": 4,
                                   "minutes": 30}],
                              report=lambda event, data: events.append((event, data)))

    assert len(rows) == 1
    assert ("booklet", {"target": 4}) in events
    assert ("generated", {"count": 1, "subject": "ریاضی", "target": 4}) in events
    assert [d["name"] for e, d in events if e == "phase"] == ["generating"]


def _fake_response(body, headers=None):
    return httpx.Response(429, json=body, headers=headers or {},
                          request=httpx.Request("POST", "https://example.test"))


def test_quota_reason_reads_googles_array_shaped_429_body():
    """Gemini wraps its error in a one-element ARRAY; the parser used to bail
    out on anything that was not an object, so the pool only ever logged a
    bare "HTTP 429" with no cause."""
    body = [{"error": {
        "code": 429,
        "message": ("You exceeded your current quota, please check your plan. "
                    "See https://ai.google.dev/gemini-api/docs/rate-limits now"),
        "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                     "violations": [{"quotaId": "GenerateRequestsPerDayPer"
                                                  "ProjectPerModel-FreeTier"}]}],
    }}]
    reason, terminal = _quota_reason(_fake_response(body))
    assert "exceeded your current quota" in reason
    assert "http" not in reason  # documentation URLs are stripped
    assert "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in reason
    assert terminal is True


def test_quota_reason_treats_a_per_minute_limit_as_retryable():
    body = {"error": {"message": "Rate limit reached for requests per minute",
                      "details": [{"quotaId": "GenerateRequestsPerMinute"
                                              "PerProjectPerModel-FreeTier"}]}}
    reason, terminal = _quota_reason(_fake_response(body))
    assert "per minute" in reason
    assert terminal is False


def test_sweep_aborts_instead_of_hammering_a_dead_provider(monkeypatch, db):
    """A refused provider used to be retried for every slot of every shelf.
    The sweep must stop after POOL_MAX_PROVIDER_FAILURES and keep the reason."""
    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 25)
    attempts = []

    def refusing_generate_one(db_, major, difficulty):
        attempts.append(major)
        pool_core.note_provider_error("HTTP 429 (daily quota exhausted)")
        return False

    monkeypatch.setattr(pool_core, "generate_one", refusing_generate_one)

    produced = pool_core.sweep(db, target=25, majors=["riazi", "tajrobi"],
                               difficulties=["easy"])

    assert produced == 0
    assert len(attempts) == pool_core.POOL_MAX_PROVIDER_FAILURES  # not 50
    snap = pool_core.progress_snapshot()
    assert snap["active"] is False  # the aborted run still closes itself
    assert snap["failures"] == pool_core.POOL_MAX_PROVIDER_FAILURES
    assert "429" in snap["last_error"]


def test_question_counters_reach_the_admin_payload(db):
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_db] = lambda: db

    assert pool_core.begin_progress("restock") is True
    pool_core.set_current("riazi", "easy")
    pool_core.start_booklet(105)
    pool_core.note_generated(30)
    pool_core.note_generated(25)
    pool_core.note_verified(24)
    pool_core.commit_questions(24)

    progress = TestClient(app).get("/api/admin/pool").json()["progress"]

    assert progress["questions"] == 24
    assert progress["questions_planned"] == 105
    assert progress["current_target"] == 105
    assert progress["current_questions"] == 55
    assert progress["current_verified"] == 24
    assert progress["phase"] == "saving"
    pool_core.finish_progress()
