"""Replanning & backlog policy tests (growth-readiness project 3).

Covers the roadmap behaviors:
- honest classification (silence = missed, 35/90 min = partially_completed)
- decision rules (>=80% done, deadline-keep, shrink after 2 misses,
  explicit drop when capacity is exhausted, adherence capacity cut)
- BOUNDED backlog: overflow is explicitly dropped, never silently carried
- ownership: user B cannot report or move user A's task
- API: report -> replan -> task moved to tomorrow with note
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.auth.database import DailyTask, SessionLocal, Base, engine  # noqa: E402
from app.planner import replan  # noqa: E402


def init_db() -> None:
    """Test-local schema init (mirrors app startup)."""
    Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Pure policy tests
# ---------------------------------------------------------------------------


def test_classification_honest_silence_is_missed():
    assert replan.classify_status(90, None) == "missed"


def test_classification_partial():
    assert replan.classify_status(90, 35) == "partially_completed"


def test_classification_80pct_counts_as_done():
    assert replan.classify_status(90, 75) == "completed"


def test_classification_count_based():
    assert replan.classify_status(60, 20, planned_count=30, completed_count=12) == "partially_completed"


def test_decision_deadline_cannot_exceed_capacity():
    d = replan.replan_decision(
        {"planned_minutes": 90, "priority": 0.4},
        capacity_left_minutes=0, missed_count=0, days_to_deadline=1,
    )
    assert d["action"] == "drop"


def test_decision_shrinks_after_two_misses():
    d = replan.replan_decision(
        {"planned_minutes": 90, "priority": 0.9},
        capacity_left_minutes=200, missed_count=2, days_to_deadline=None,
    )
    assert d["action"] == "shrink"
    assert d["new_minutes"] == 54


def test_decision_drop_low_priority_when_full():
    d = replan.replan_decision(
        {"planned_minutes": 60, "priority": 0.3},
        capacity_left_minutes=0, missed_count=0, days_to_deadline=None,
    )
    assert d["action"] == "drop"


def test_decision_high_priority_cannot_exceed_capacity():
    d = replan.replan_decision(
        {"planned_minutes": 60, "priority": 0.9},
        capacity_left_minutes=0, missed_count=0, days_to_deadline=None,
    )
    assert d["action"] == "drop"


def test_backlog_bounded_overflow_explicitly_dropped():
    """The core roadmap invariant: backlog never grows silently."""
    missed = [
        {"id": i, "description": f"t{i}", "subject": "ریاضی",
         "planned_minutes": 60, "priority": 0.5 + i * 0.01,
         "missed_count": 0}
        for i in range(10)  # 600 minutes of backlog
    ]
    res = replan.resolve_backlog(missed, capacity_minutes=120, adherence=1.0)
    assert res["capacity_minutes"] == 120
    total_planned = sum(t["planned_minutes"] for t in res["carried"]) + \
        sum(t["decision"]["new_minutes"] for t in res["shrunk"])
    assert total_planned <= 120
    assert len(res["dropped"]) >= 1   # overflow explicitly dropped
    for d in res["dropped"]:
        assert d["decision"]["note"]  # every drop carries a visible reason


def test_backlog_deadline_task_prioritized_within_capacity():
    missed = [
        {"id": "a", "description": "کنکور", "planned_minutes": 90,
         "priority": 0.4, "missed_count": 0, "days_to_deadline": 1},
        {"id": "b", "description": "عادی", "planned_minutes": 60,
         "priority": 0.9, "missed_count": 0},
    ]
    res = replan.resolve_backlog(missed, capacity_minutes=60, adherence=1.0)
    assert res["shrunk"][0]["id"] == "a"
    assert res["shrunk"][0]["decision"]["new_minutes"] == 60
    assert res["dropped"][0]["id"] == "b"


def test_low_adherence_shrinks_capacity_with_floor():
    cap = replan.next_day_capacity(180, adherence=0.4)
    assert 90 <= cap < 180  # cut but never below 50% floor
    assert replan.next_day_capacity(180, adherence=1.0) == 180


def test_determinism():
    backlog = [{"id": f"t{i}", "description": "x", "planned_minutes": 45,
                "priority": 0.5, "missed_count": 1} for i in range(6)]
    r1 = replan.resolve_backlog(backlog, capacity_minutes=100, adherence=0.8)
    r2 = replan.resolve_backlog(backlog, capacity_minutes=100, adherence=0.8)
    assert r1 == r2


# ---------------------------------------------------------------------------
# API tests (router functions called directly, project test convention)
# ---------------------------------------------------------------------------


class _Ctx:
    """Fake auth context matching the tests' direct-call convention."""

    def __init__(self, user_id: int):
        self.id = user_id


def _mk_task(user_id, **kw):
    db = SessionLocal()
    t = DailyTask(user_id=user_id, date=kw.get("date") or __import__("datetime").date.today(),
                  subject=kw.get("subject", "فیزیک"),
                  task_type=kw.get("task_type", "study"),
                  description=kw.get("description", "گرما و ترمودینامیک"),
                  duration_minutes=kw.get("duration_minutes", 90),
                  status="planned")
    db.add(t)
    db.commit()
    db.refresh(t)
    tid = t.id
    db.close()
    return tid


def test_report_and_replan_end_to_end(tmp_path):
    from app.routers.tasks import report_task, replan_backlog, get_backlog  # noqa: F401
    init_db()
    uid = 990001
    db = SessionLocal()
    db.query(DailyTask).filter(DailyTask.user_id == uid).delete()
    db.commit()
    db.close()

    # Task planned for YESTERDAY, never reported -> silence = missed.
    import datetime as dt
    tid = _mk_task(uid, date=dt.date.today() - dt.timedelta(days=1),
                   duration_minutes=90)

    out = replan_backlog(
        _FakeReq(), _Ctx(uid), db=SessionLocal())
    assert out["tomorrow"] == (dt.date.today() + dt.timedelta(days=1)).isoformat()
    # Zero reported minutes -> adherence floor 0.25 -> the honest engine
    # SHRINKS the never-touched 90-min task instead of carrying it whole.
    assert len(out["shrunk"]) == 1, out
    moved = out["shrunk"][0]
    assert moved["minutes"] == 54  # max(25, int(90*0.6))
    assert moved["note"]

    db = SessionLocal()
    t = db.query(DailyTask).get(tid)
    assert t.status == "rescheduled"
    assert (t.date - dt.date.today()).days == 1   # moved to tomorrow
    assert t.replan_note
    db.close()


class _FakeReq:
    capacity_minutes = 180
    adherence = None


def test_partial_report_splits_remainder():
    from app.routers.tasks import report_task, replan_backlog
    init_db()
    uid = 990002
    db = SessionLocal()
    db.query(DailyTask).filter(DailyTask.user_id == uid).delete()
    db.commit()
    db.close()

    import datetime as dt
    tid = _mk_task(uid, date=dt.date.today() - dt.timedelta(days=1),
                   duration_minutes=90)
    rep = report_task(tid, _Report(actual_minutes=35), _Ctx(uid),
                      db=SessionLocal())
    assert rep["task"]["status"] == "partially_completed"

    out = replan_backlog(_FakeReq(), _Ctx(uid), db=SessionLocal())
    # The remainder (90-35=55) is what moves to tomorrow.
    assert len(out["carried"]) + len(out["shrunk"]) == 1
    assert out["carried"] and out["carried"][0]["minutes"] == 55, out


def test_ownership_user_b_cannot_touch_user_a():
    from app.routers.tasks import report_task
    init_db()
    uid_a, uid_b = 990003, 990004
    import datetime as dt
    tid = _mk_task(uid_a, date=dt.date.today() - dt.timedelta(days=1))
    rep = report_task(tid, _Report(actual_minutes=90), _Ctx(uid_b),
                      db=SessionLocal())
    assert rep == {"error": "Task not found"}


class _Report:
    def __init__(self, actual_minutes=None, completed_count=None,
                 planned_count=None, reason=None, energy=None):
        self.actual_minutes = actual_minutes
        self.completed_count = completed_count
        self.planned_count = planned_count
        self.reason = reason
        self.energy = energy


def test_miss_count_grows_and_shrinks_on_replan():
    from app.routers.tasks import report_task, replan_backlog
    init_db()
    uid = 990005
    db = SessionLocal()
    db.query(DailyTask).filter(DailyTask.user_id == uid).delete()
    db.commit()
    db.close()

    import datetime as dt
    tid = _mk_task(uid, date=dt.date.today() - dt.timedelta(days=1),
                   duration_minutes=120)
    report_task(tid, _Report(actual_minutes=0), _Ctx(uid), db=SessionLocal())
    db = SessionLocal()
    t = db.query(DailyTask).get(tid)
    assert t.miss_count == 1
    db.close()

    replan_backlog(_FakeReq(), _Ctx(uid), db=SessionLocal())
    db = SessionLocal()
    t = db.query(DailyTask).get(tid)
    assert t.status == "rescheduled"
    previous_minutes = t.duration_minutes
    db.close()

    # Miss it AGAIN on the new date, replan again -> now it must SHRINK
    # (2 consecutive misses = task too big).
    db = SessionLocal()
    t = db.query(DailyTask).get(tid)
    t.status = "missed"
    t.miss_count = 2
    t.date = dt.date.today() - dt.timedelta(days=1)
    db.commit()
    db.close()

    out = replan_backlog(_FakeReq(), _Ctx(uid), db=SessionLocal())
    shrunk = out["shrunk"]
    assert shrunk and shrunk[0]["minutes"] == max(25, int(previous_minutes * 0.6)), out  # shrink current remaining work



def test_urgent_and_repeatedly_missed_work_never_exceeds_small_capacity():
    tasks = [{"id":i,"planned_minutes":90,"priority":0.9,"missed_count":3,"days_to_deadline":1} for i in range(5)]
    for capacity in (0, 10, 25, 75):
        result = replan.resolve_backlog(tasks, capacity_minutes=capacity)
        minutes = sum(t["planned_minutes"] for t in result["carried"]) + sum(t["decision"]["new_minutes"] for t in result["shrunk"])
        assert minutes <= capacity
