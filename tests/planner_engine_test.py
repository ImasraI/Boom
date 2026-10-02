"""Growth-readiness project 2: deterministic planner invariants.

Every test asserts a HARD constraint of the roadmap document:
  - same input -> byte-identical plan (determinism)
  - no overlap between items or with fixed events
  - nothing outside wake..sleep; daily load <= capacity
  - a test never precedes its topic's study
  - unowned resources are never scheduled (reported honestly instead)
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

from app.planner.engine import (
    CandidateTask, FixedEvent, PlannerInput, generate_plan, priority_of,
    validate_plan_items,
)


PROFILE = {"wake": "06:30", "sleep": "23:00", "daily_hours": {"*": 6}}


def _plan(tasks, fixed=None, studied=frozenset(), profile=None, start=None):
    return generate_plan(PlannerInput(
        profile=profile or PROFILE,
        fixed_events=fixed or [],
        tasks=tasks,
        studied_topics=set(studied),
        start_date=start or "2099-01-06",  # a future Monday: deterministic
    ))


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# --- Thin-fragment policy --------------------------------------------------
# The weekly plan used to be full of 30-minute blocks because a package whose
# total slightly exceeded the block cap was split into a full block plus a stub
# (105 -> 90+15), and the stub often spilled into the next day as a lone
# 15-minute block. The policy is OFF unless the caller asks for it (see
# PlannerInput.min_block_minutes), so an explicit user-chosen block length
# (25-minute pomodoro) is never second-guessed.

def _policy_plan(tasks, profile=None, cap=90, min_block=30, hard_max=120):
    return generate_plan(PlannerInput(
        profile=profile or {"wake": "06:00", "sleep": "23:00",
                            "daily_hours": {"*": 4}},
        tasks=tasks,
        max_block_minutes=cap,
        default_break_minutes=15,
        min_block_minutes=min_block,
        hard_max_block_minutes=hard_max,
        start_date="2099-01-06",
    ))


def _one_task(minutes):
    return CandidateTask(id="a", subject="ریاضی", topic="حد",
                         planned_minutes=minutes, weakness=0.9).__dict__


def test_block_absorbs_its_own_leftover_instead_of_emitting_a_stub():
    # 105 minutes of work, a 90-minute standard: ONE 105-minute block, not the
    # 90+15 split that put a 15-minute block on the grid.
    result = _policy_plan([_one_task(105)])
    assert [i["planned_minutes"] for i in result.items] == [105]


def test_a_split_leaves_a_full_size_block_not_a_stub():
    # Only 90 minutes of room per day for a 105-minute task: cut the first
    # block shorter so the leftover is a real block (75+30), not 90+15.
    result = _policy_plan(
        [_one_task(105)],
        profile={"wake": "06:00", "sleep": "23:00", "daily_hours": {"*": 1.5}},
    )
    parts = sorted(i["planned_minutes"] for i in result.items)
    assert parts == [30, 75]
    assert sum(parts) == 105  # no minute is lost to the policy


def test_policy_off_keeps_an_explicit_block_length_untouched():
    # A student on 25-minute pomodoro wants 25-minute blocks: no merging, no
    # dropped leftovers (this is what broke when the floor was unconditional).
    result = _policy_plan(
        [_one_task(60)], cap=25, min_block=0, hard_max=0,
        profile={"wake": "06:00", "sleep": "23:00", "daily_hours": {"*": 1.5}},
    )
    parts = sorted(i["planned_minutes"] for i in result.items)
    assert 25 in parts and sum(parts) == 60


def test_determinism_same_input_same_output():
    tasks = [CandidateTask(id="a", subject="حسابان", topic="مشتق",
                           planned_minutes=90, weakness=0.8).__dict__]
    r1 = _plan([dict(t) for t in tasks])
    r2 = _plan([dict(t) for t in tasks])
    assert r1.to_dict() == r2.to_dict()


def test_priority_formula_matches_documented_weights():
    t = {"weakness": 1.0, "task_type": "study"}
    # 0.25 weakness + 0.15 prerequisite(study) = 0.40
    assert priority_of(t) == 0.4
    urgent = {"deadline": "2099-01-01", "task_type": "review"}
    # deadline far future => urgency 0 (beyond horizon)
    assert priority_of(urgent) == 0.0


def test_no_overlap_with_fixed_events_or_items():
    fixed = [{"date": "2099-01-06", "start": "08:00", "end": "13:00",
              "title": "مدرسه", "kind": "school"}]
    tasks = [{"id": "t1", "subject": "حسابان", "planned_minutes": 120}]
    r = _plan(tasks, fixed=fixed)
    assert r.items, "plan must schedule something"
    for it in r.items:
        assert it["date"] == "2099-01-06"
        # School 08-13: nothing may overlap it.
        assert not (_minutes(it["start"]) < 13 * 60 and _minutes(it["end"]) > 8 * 60), it
    # Items must not overlap each other.
    ordered = sorted(r.items, key=lambda i: i["start"])
    for a, b in zip(ordered, ordered[1:]):
        assert _minutes(a["end"]) <= _minutes(b["start"]), (a, b)


def test_never_outside_wake_sleep_window():
    tasks = [{"id": "t1", "subject": "شیمی", "planned_minutes": 600}]
    r = _plan(tasks)
    for it in r.items:
        assert _minutes(it["start"]) >= 6 * 60 + 30
        assert _minutes(it["end"]) <= 23 * 60


def test_daily_capacity_respected():
    profile = {"wake": "06:30", "sleep": "23:00", "daily_hours": {"*": 2}}
    tasks = [{"id": "t1", "subject": "حسابان", "planned_minutes": 600}]
    r = _plan(tasks, profile=profile)
    by_day = {}
    for it in r.items:
        by_day[it["date"]] = by_day.get(it["date"], 0) + it["planned_minutes"]
    assert by_day and all(v <= 120 for v in by_day.values())


def test_test_never_scheduled_before_topic_study():
    tasks = [
        {"id": "t1", "subject": "فیزیک", "topic": "دینامیک",
         "task_type": "test", "planned_minutes": 60},
    ]
    r = _plan(tasks)  # no studied topics
    assert not r.items
    assert r.unscheduled == [{"id": "t1", "reason": "test_before_study"}]
    # With the topic studied first, the test fits.
    r2 = _plan(tasks, studied={"دینامیک"})
    assert any(i["task_type"] == "test" for i in r2.items)


def test_unowned_resource_never_scheduled():
    tasks = [{"id": "t1", "subject": "زیست", "planned_minutes": 60,
              "resource": "کتاب غایب", "resource_owned": False}]
    r = _plan(tasks)
    assert not r.items
    assert r.unscheduled[0]["reason"] == "resource_not_owned"


def test_long_tasks_split_into_blocks():
    tasks = [{"id": "t1", "subject": "حسابان", "topic": "حد",
              "planned_minutes": 180}]
    r = _plan(tasks)
    assert len(r.items) >= 2
    assert all(i["planned_minutes"] <= 90 for i in r.items)
    assert sum(i["planned_minutes"] for i in r.items) == 180


def test_validator_rejects_bad_agent_proposals():
    profile = {"wake": "06:30", "sleep": "23:00"}
    fixed = [{"date": "2099-01-06", "start": "09:00", "end": "12:00",
              "title": "کلاس"}]
    ok = [{"id": "x", "date": "2099-01-06", "start": "14:00", "end": "16:00"}]
    assert validate_plan_items(ok, profile, fixed)["valid"] is True
    overlapping = [{"id": "x", "date": "2099-01-06", "start": "10:00", "end": "11:00"}]
    res = validate_plan_items(overlapping, profile, fixed)
    assert not res["valid"] and any("fixed event" in v for v in res["violations"])
    late = [{"id": "y", "date": "2099-01-06", "start": "22:00", "end": "23:30"}]
    res2 = validate_plan_items(late, profile, fixed)
    assert not res2["valid"] and any("wake/sleep" in v for v in res2["violations"])


def test_overcapacity_proposal_rejected_by_validator():
    profile = {"wake": "06:30", "sleep": "23:00"}
    items = [
        {"id": "a", "date": "2099-01-06", "start": "07:00", "end": "09:00",
         "planned_minutes": 120},
        {"id": "b", "date": "2099-01-06", "start": "10:00", "end": "12:00",
         "planned_minutes": 120},
        {"id": "c", "date": "2099-01-06", "start": "13:00", "end": "15:00",
         "planned_minutes": 120},
        {"id": "d", "date": "2099-01-06", "start": "16:00", "end": "18:00",
         "planned_minutes": 120},
        {"id": "e", "date": "2099-01-06", "start": "18:30", "end": "19:30",
         "planned_minutes": 61},
    ]
    res = validate_plan_items(items, profile, [], daily_cap=480)
    assert not res["valid"]
    assert any("capacity" in v for v in res["violations"])


def test_multiple_tasks_do_not_share_a_slot():
    r = _plan([{"id": str(i), "subject": "math", "planned_minutes": 60} for i in range(3)])
    assert validate_plan_items(r.items, PROFILE, [])["valid"]


def test_partial_work_carries_forward_without_repeating_or_duplicate_ids():
    r = _plan([{"id": "a", "subject": "math", "planned_minutes": 300, "target_count": 50}],
              profile={"daily_hours": {"*": 2}})
    assert sum(i["planned_minutes"] for i in r.items) == 300
    assert sum(i["target_count"] for i in r.items) == 50
    assert len({i["id"] for i in r.items}) == len(r.items)
    assert all(i["parts"] == len(r.items) for i in r.items)


def test_zero_hours_means_a_rest_day():
    r = _plan([{"id": "a", "subject": "math", "planned_minutes": 60}],
              profile={"daily_hours": {"*": 0}})
    assert not r.items
    assert r.unscheduled[0]["remaining_minutes"] == 60


def test_urgent_test_waits_for_full_study_then_runs():
    r = _plan([
        {"id": "test", "subject": "math", "topic": "limits", "task_type": "test",
         "weakness": 1, "overdue": 1, "planned_minutes": 60},
        {"id": "study", "subject": "math", "topic": "limits", "task_type": "study",
         "planned_minutes": 180},
    ], profile={"daily_hours": {"*": 2}})
    studies = [i for i in r.items if i["task_type"] == "study"]
    tests = [i for i in r.items if i["task_type"] == "test"]
    assert tests and not r.unscheduled
    assert (tests[0]["date"], tests[0]["start"]) >= (studies[-1]["date"], studies[-1]["end"])


def test_review_does_not_unlock_an_unstudied_topic():
    r = _plan([
        {"id": "review", "subject": "math", "topic": "limits", "task_type": "review", "weakness": 1},
        {"id": "test", "subject": "math", "topic": "limits", "task_type": "test"},
    ])
    assert not any(i["task_type"] == "test" for i in r.items)


def test_deadline_priority_uses_plan_start_date():
    r = _plan([
        {"id": "later", "subject": "a", "deadline": "2099-01-18"},
        {"id": "soon", "subject": "z", "deadline": "2099-01-07"},
    ])
    assert r.items[0]["id"].startswith("soon#")


def test_small_remainder_is_not_lost():
    r = _plan([{"id": "a", "subject": "math", "planned_minutes": 100}])
    assert sum(i["planned_minutes"] for i in r.items) == 100
    assert not r.unscheduled


def test_validator_uses_elapsed_time_not_claimed_minutes():
    items = [{"id": "a", "date": "2099-01-06", "start": "07:00", "end": "10:00", "planned_minutes": 1}]
    assert not validate_plan_items(items, PROFILE, [], daily_cap=120)["valid"]


def test_overnight_window_respects_next_calendar_day_events():
    profile = {"wake": "22:00", "sleep": "02:00", "daily_hours": {"*": 3}}
    fixed = [{"date": "2099-01-07", "start": "00:00", "end": "01:00"}]
    r = _plan([{"id": "a", "subject": "math", "planned_minutes": 180}], profile=profile, fixed=fixed)
    assert sum(i["planned_minutes"] for i in r.items) == 180
    assert validate_plan_items(r.items, profile, fixed)["valid"]


def test_same_named_topic_in_another_subject_does_not_unlock_test():
    r = _plan([{"id": "a", "subject": "math", "topic": "intro"},
               {"id": "b", "subject": "physics", "topic": "intro", "task_type": "test"}])
    assert not any(i["subject"] == "physics" for i in r.items)


def test_validator_reports_malformed_times_instead_of_crashing():
    assert not validate_plan_items([{"date": "bad", "start": "xx", "end": "25:00"}], PROFILE, [])["valid"]


def test_varied_schedules_preserve_work_and_constraints():
    import random
    rng = random.Random(42)
    for case in range(40):
        tasks = [{"id": str(i), "subject": str(i % 3), "planned_minutes": rng.randint(1, 400),
                  "target_count": rng.randint(0, 100), "weakness": rng.random()} for i in range(8)]
        profile = {"wake": "07:00", "sleep": "22:00", "daily_hours": {str(d): rng.randint(0, 6) for d in range(7)}}
        r = _plan(tasks, profile=profile)
        assert validate_plan_items(r.items, profile, [])["valid"], case
        for t in tasks:
            done = sum(i["planned_minutes"] for i in r.items if i["id"].startswith(t["id"] + "#"))
            remaining = sum(i.get("remaining_minutes", 0) for i in r.unscheduled if i["id"] == t["id"])
            assert done + remaining == t["planned_minutes"]
        assert len({i["id"] for i in r.items}) == len(r.items)
