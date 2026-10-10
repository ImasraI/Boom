"""Exercise reuse, per-question quarantine, permissions, and targeted runs."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.database import (Base, BankQuestion, QuestionReport, GeneratedMock,
    MockAttempt, ArenaMatch, User, get_db)
from app.auth.deps import get_current_user
from app.rag import question_bank as bank, pool_core, mock_generation
from app.routers import mocks, admin, arena


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([User(id=i, username=f"bank-user-{i}", hashed_password="x", is_admin=(i == 3)) for i in (0, 1, 2, 3)])
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture(autouse=True)
def pool_state():
    pool_core.clear_cancel()
    pool_core.finish_progress()
    yield
    pool_core.clear_cancel()
    pool_core.finish_progress()


def make_mock(db, *, owner=0, status="pending_use", difficulty="konkur", count=3, label="old", grade="دوازدهم", verified=True, figure=None):
    questions = [{"_id": i + 1, "subject": "ریاضی", "topic": "تابع", "text": f"{label} question {i}",
        "options": ["a", "b", "c", "d"], "answer": 1, "explanation": "why",
        "verification_status": "verified" if verified else "unverified"} for i in range(count)]
    if figure is not None:
        for question in questions:
            question['figure'] = figure
    row = GeneratedMock(student_id=owner, title=label, major=pool_core.CANONICAL_MAJOR["riazi"],
        grade=grade, duration_minutes=10, difficulty=difficulty, status=status,
        bank_scope="shared" if owner == 0 else "private", questions=json.dumps(questions))
    db.add(row); db.flush(); bank.index_mock(db, row); db.commit()
    return row


def test_question_diagram_survives_storage_public_booklet_and_answer_review(db):
    figure = {'type':'geometry','data':{'shape':'triangle',
        'points':{'A':[0,0],'B':[4,0],'C':[0,3]},
        'side_lengths':{'AB':4,'AC':3,'BC':5},'marks':{'right_angle_at':'A'}}}
    mock = make_mock(db, owner=1, status='claimed', count=1, figure=figure)
    content = json.loads(db.query(BankQuestion).one().content)
    assert content['figure'] == figure
    visible = mocks.get_mock(mock.id, db.get(User,1), db)['questions'][0]
    assert visible['figure'] == figure
    assert 'answer' not in visible and 'explanation' not in visible
    result = mocks.submit_mock(mock.id, mocks.SubmitPayload(answers={'1':1}), db.get(User,1), db)
    assert result['correct'] == 1 and result['review'][0]['figure'] == figure
    assert result['review'][0]['answer'] == 1
    with pytest.raises(HTTPException) as error:
        mocks.get_mock(mock.id, db.get(User,2), db)
    assert error.value.status_code == 404


def test_legacy_question_without_diagram_remains_readable(db):
    mock = make_mock(db, owner=1, status='claimed', count=1)
    assert mocks.get_mock(mock.id, db.get(User,1), db)['questions'][0]['figure'] == {'type':'none','data':{}}


PLAN = [{"name": "ریاضی", "questions": 2, "minutes": 10}]
MAJORS = [pool_core.CANONICAL_MAJOR["riazi"]]


def test_mock_stock_only_refuses_empty_bank_without_any_provider_call(db, monkeypatch):
    monkeypatch.setattr(mock_generation, 'generate_booklet', lambda *a, **kw: pytest.fail('No live drafting'))
    with pytest.raises(HTTPException) as error:
        mocks._generate_reserved_mock(mocks.MockConfig(total_questions=5,stock_only=True),db.get(User,1),db)
    assert error.value.status_code==409 and error.value.detail['code']=='pool_empty'


def test_full_mock_cannot_claim_a_short_subject_template(db):
    source=make_mock(db,count=1)
    assert mocks._claim_pool_mock(db,1,'riazi','konkur','دوازدهم',PLAN) is None
    db.refresh(source)
    assert source.status=='pending_use'  # Still useful bank stock, not corrupt.


def test_stock_inventory_excludes_unverified_corrupt_and_private_questions(db):
    good=make_mock(db,count=3)
    make_mock(db,count=7,label='unverified',verified=False)
    make_mock(db,owner=1,status='claimed',count=4,label='private')
    bank.record_report(db,good,1,1,'broken question')
    inventory=pool_core.stock_inventory(db)
    assert sum(row['verified'] for row in inventory)==2
    assert sum(row['unused'] for row in inventory)==2


def test_ranked_stock_only_rejects_insufficient_subject_stock_before_charge(db, monkeypatch):
    make_mock(db,count=1)
    monkeypatch.setattr(arena,'get_settings',lambda:SimpleNamespace(POOL_ALLOW_LIVE_GENERATION=False))
    monkeypatch.setattr(arena,'consume_ai_use',lambda *a:pytest.fail('Do not charge an unavailable duel'))
    with pytest.raises(HTTPException) as error:
        arena.join_queue(arena.JoinPayload(student={'major':MAJORS[0],'grade':'دوازدهم'}),db.get(User,1),db)
    assert error.value.status_code==409 and error.value.detail['code']=='pool_empty'


def test_admin_reports_unlimited_capacity_and_actual_verified_stock(db):
    make_mock(db,count=3)
    result=admin.pool_levels(db)
    assert result['unlimited_storage'] and result['progress']['capacity'] is None
    assert result['progress']['duel_capacity'] is None
    assert sum(s['verified'] for s in result['inventory'])==3
    assert next(s for s in result['catalog'] if s['key']=='riazi')['ranked_questions']==34


def test_ranked_subject_filter_does_not_search_for_subject_name_inside_lesson(db):
    make_mock(db,count=3)
    plan=[{'name':'ریاضی','questions':2,'minutes':10,'topics':['ریاضی']}]
    questions=bank.assemble(db,1,plan,MAJORS,topics=['ریاضی'],shared_only=True)
    assert len(questions)==2 and all(q['topic']=='تابع' for q in questions)


def test_ranked_geometry_filter_applies_only_to_math_not_other_subjects(db):
    source=make_mock(db,count=2)
    questions=json.loads(source.questions)
    for q in questions:
        q.pop('bank_id',None); q['topic']='هندسه'; q['text']+=' geometry'
    questions += [{**q,'subject':'فیزیک','topic':'حرکت','text':'physics '+q['text']} for q in questions[:]]
    source.questions=json.dumps(questions); source.bank_indexed=False; bank.index_mock(db,source); db.commit()
    plan=[{'name':'ریاضی','questions':2,'minutes':10,'topics':['هندسه']},
          {'name':'فیزیک','questions':2,'minutes':10,'topics':['فیزیک']}]
    selected=bank.assemble(db,1,plan,MAJORS,topics=['هندسه','فیزیک'],shared_only=True)
    assert len(selected)==4
    assert all(q['topic']=='هندسه' for q in selected if q['subject']=='ریاضی')


def test_five_konkur_style_questions_are_assembled_from_shared_pool(db, monkeypatch):
    source = make_mock(db, count=5, label='pool math')
    questions = json.loads(source.questions)
    for subject in ('فیزیک', 'شیمی'):
        questions += [{**{k:v for k,v in q.items() if k!='bank_id'}, '_id':len(questions)+i+1, 'subject':subject,
            'text':subject+' question '+str(i)} for i,q in enumerate(questions[:5])]
    source.questions=json.dumps(questions); source.bank_indexed=False
    bank.index_mock(db, source); db.commit()
    monkeypatch.setattr(mocks, 'require_pool_available', lambda: pytest.fail('Ready pool stock needs no provider'))
    config=mocks.MockConfig(mode='general', total_questions=5,
        student={'major':MAJORS[0], 'grade':'دوازدهم'})
    result=mocks._generate_reserved_mock(config, db.get(User,1), db)
    assert result['total_questions']==5 and result['source']=='question_bank'
    assert sum(s['questions'] for s in result['subjects'])==5
    assert result['duration_minutes'] < 145
    assert source.student_id==0
    visible=mocks.get_mock(result['mock_id'], db.get(User,1), db)
    assert len(visible['questions'])==5 and all('answer' not in q for q in visible['questions'])


@pytest.mark.parametrize('total',[1,2,5,10,105,200])
def test_total_count_is_independent_of_konkur_style(total):
    poolable, plan, _=mocks._resolve_plan(mocks.MockConfig(total_questions=total))
    assert not poolable
    assert sum(s['questions'] for s in plan)==min(total,105)
    assert all(s['questions'] > 0 for s in plan)


def test_general_prefers_unused_stock_while_practice_prefers_used_stock(db, monkeypatch):
    old=make_mock(db,count=5,label='used')
    bank.mark_used(db, bank.active_questions(db,old)); db.commit()
    make_mock(db,count=5,label='fresh')
    monkeypatch.setattr(mocks,'require_pool_available',lambda:pytest.fail('Stock available'))
    result=mocks._generate_reserved_mock(mocks.MockConfig(mode='general', subjects=['ریاضی'],
        total_questions=5, student={'major':MAJORS[0],'grade':'دوازدهم'}),db.get(User,1),db)
    questions=json.loads(db.get(GeneratedMock,result['mock_id']).questions)
    assert all(q['text'].startswith('fresh') for q in questions)


def test_weakness_practice_retains_explicit_total_count(db, monkeypatch):
    make_mock(db, count=10, label='weakness')
    monkeypatch.setattr(mocks.mock_generation,'weak_areas',lambda _: [{'subject':'ریاضی','topic':'تابع','hits':5,'weight':5}])
    monkeypatch.setattr(mocks,'require_pool_available',lambda:pytest.fail('Stock available'))
    result=mocks._generate_reserved_mock(mocks.MockConfig(mode='practice_weak_areas',subjects=['ریاضی'],
        total_questions=5,student={'major':MAJORS[0],'grade':'دوازدهم'}),db.get(User,1),db)
    assert result['total_questions']==5


def test_one_report_excludes_only_that_question_from_all_copies(db):
    source = make_mock(db)
    questions = bank.active_questions(db, source)
    clone = bank.create_reused_mock(db, 1, questions, MAJORS[0], "دوازدهم", "konkur", 10)
    db.commit()
    result = mocks.report_question(clone.id, 1, mocks.QuestionReportIn(reason="answer is incorrect"), db.get(User, 1), db)
    assert result["status"] == "corrupt"
    assert db.query(BankQuestion).count() == 3
    assert len(json.loads(source.questions)) == 3  # historical snapshot preserved
    assert len(bank.active_questions(db, source)) == 2
    assert len(bank.active_questions(db, clone)) == 2
    selected = bank.assemble(db, 2, PLAN, MAJORS, used_only=True)
    assert len(selected) == 2 and all(q["bank_id"] != result["question_id"] for q in selected)
    visible = mocks.get_mock(clone.id, db.get(User, 1), db)
    assert len(visible["questions"]) == 2
    assert all("answer" not in q and "explanation" not in q for q in visible["questions"])
    mocks.report_question(clone.id, 1, mocks.QuestionReportIn(reason="still incorrect"), db.get(User, 1), db)
    assert db.query(QuestionReport).count() == 1


def test_question_reports_require_access_to_the_source_exam(db):
    source = make_mock(db, owner=1, status="claimed")
    with pytest.raises(HTTPException) as e:
        mocks.report_question(source.id, 1, mocks.QuestionReportIn(reason="wrong answer"), db.get(User, 2), db)
    assert e.value.status_code == 404
    assert db.query(QuestionReport).count() == 0
    db.add(ArenaMatch(student_a_id=1, student_b_id=2, mock_id=source.id, status="pending")); db.commit()
    assert mocks.report_question(source.id, 1, mocks.QuestionReportIn(reason="wrong answer"), db.get(User, 2), db)["ok"]


def test_private_questions_are_reusable_only_by_their_owner(db):
    source = make_mock(db, owner=1, status="claimed")
    assert len(bank.assemble(db, 1, PLAN, MAJORS, used_only=True)) == 2
    assert bank.assemble(db, 2, PLAN, MAJORS, used_only=True) == []
    assert bank.assemble(db, 1, PLAN, MAJORS, shared_only=True) == []
    assert source.student_id == 1


def test_ai_practice_reuses_own_private_questions_without_sharing_them_in_ranked(db):
    make_mock(db, owner=1, status="claimed")
    practice = pool_core.reused_duel(db, 1, "riazi", plan=PLAN, used_only=True, prefer_used=True)
    db.commit()
    assert practice is not None and practice.bank_scope == "private"
    assert len(json.loads(practice.questions)) == 2
    assert pool_core.reused_duel(db, 2, "riazi", plan=PLAN, prefer_used=True) is None
    assert pool_core.reused_duel(db, 1, "riazi", plan=PLAN) is None


def test_background_session_failure_releases_generation_slot(monkeypatch):
    from app.auth import database
    from app import main

    def unavailable():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(database, "SessionLocal", unavailable)
    monkeypatch.setattr(admin.pool_service, "SessionLocal", unavailable)
    monkeypatch.setattr(admin, "require_pool_available", lambda: None)
    # Run the actual background callback synchronously to verify its failure
    # cleanup, without introducing a real thread into the unit test.
    monkeypatch.setattr(admin.threading, "Thread", lambda *, target, **kw: SimpleNamespace(start=target))
    assert admin.pool_restock(None, admin.PoolRunIn(count=1))["started"]
    assert not admin._restock_running and not pool_core.progress_snapshot()["active"]
    main._run_pool_sweep_once()
    assert not pool_core.progress_snapshot()["active"]


def test_practice_uses_old_questions_before_fresh_even_when_provider_is_unavailable(db, monkeypatch):
    old = make_mock(db, label="used")
    bank.mark_used(db, bank.active_questions(db, old)); db.commit()
    make_mock(db, label="fresh")
    monkeypatch.setattr(mocks, "require_pool_available", lambda: pytest.fail("Reuse must not call provider"))
    config = mocks.MockConfig(mode="practice", subjects=["ریاضی"], questions_per_subject=2,
        student={"major": MAJORS[0], "grade": "دوازدهم"})
    result = mocks._generate_reserved_mock(config, db.get(User, 1), db)
    selected = json.loads(db.get(GeneratedMock, result["mock_id"]).questions)
    assert len(selected) == 2 and all(q["text"].startswith("used") for q in selected)
    assert result["source"] == "question_bank"
    assert old.student_id == 0  # Reuse never steals the original owner's row.


def test_practice_reports_actual_smaller_bank_size_without_fake_questions(db, monkeypatch):
    old = make_mock(db, count=1)
    bank.mark_used(db, bank.active_questions(db, old)); db.commit()
    monkeypatch.setattr(mocks, "require_pool_available", lambda: pytest.fail("Reuse must not call provider"))
    result = mocks._generate_reserved_mock(mocks.MockConfig(mode="practice", questions_per_subject=5), db.get(User, 1), db)
    assert result["total_questions"] == 1 and result["subjects"][0]["questions"] == 1


def test_practice_uses_fresh_verified_stock_when_nothing_has_been_used(db, monkeypatch):
    make_mock(db, count=2, label="fresh")
    monkeypatch.setattr(mocks, "require_pool_available", lambda: pytest.fail("Stock must not call provider"))
    result = mocks._generate_reserved_mock(mocks.MockConfig(mode="practice"), db.get(User, 1), db)
    assert result["total_questions"] == 2
    assert result["source"] == "question_bank"


def test_mock_generation_prefers_saved_grade_over_stale_browser_profile(db, monkeypatch):
    from app.auth.database import StudentProfile
    db.add(StudentProfile(user_id=1, major=MAJORS[0], grade="دهم")); db.commit()
    make_mock(db, grade="دهم", label="tenth")
    make_mock(db, grade="دوازدهم", label="twelfth")
    monkeypatch.setattr(mocks, "require_pool_available", lambda: pytest.fail("Stock must not call provider"))
    result = mocks._generate_reserved_mock(mocks.MockConfig(mode="practice",
        student={"major":"علوم تجربی", "grade":"دوازدهم"}), db.get(User, 1), db)
    exam = db.get(GeneratedMock, result["mock_id"])
    assert exam.grade == "دهم" and exam.major == MAJORS[0]
    assert all(q["text"].startswith("tenth") for q in json.loads(exam.questions))


@pytest.mark.parametrize("failure", ["empty", "exception", "partial", "daily_quota"])
def test_failed_ranked_generation_cancels_without_scores_and_preserves_verified_survivors(db, monkeypatch, failure):
    from sqlalchemy.orm import sessionmaker
    source = make_mock(db, owner=1, status="claimed", count=1)
    match = ArenaMatch(student_a_id=1, student_b_id=2, mock_id=source.id, status="pending")
    db.add(match); db.commit()
    monkeypatch.setattr(arena, "SessionLocal", sessionmaker(bind=db.get_bind()))
    def generate(*a, **kw):
        if failure == "daily_quota": pytest.fail("Must not probe a blocked provider")
        if failure == "exception": raise RuntimeError("provider unavailable")
        return json.loads(source.questions) if failure == "partial" else []
    monkeypatch.setattr(mock_generation, "generate_booklet", generate)
    monkeypatch.setattr(mock_generation, "verify_and_repair_booklet", lambda qs, *a, **kw: qs)
    def unavailable():
        if failure == "daily_quota": raise HTTPException(503, detail="daily quota")
    monkeypatch.setattr(arena, "require_pool_available", unavailable)
    monkeypatch.setattr(arena, "pool_quota_status", lambda: {"blocked":failure == "daily_quota"})
    arena._generate_duel_booklet(match, PLAN)
    db.expire_all(); stored=db.get(ArenaMatch, match.id)
    assert stored.status == "cancelled" and stored.generation_error
    assert stored.score_a is None and stored.score_b is None
    assert stored.delta_a == stored.delta_b == 0
    assert db.get(User, 1).rating == db.get(User, 2).rating == 1000
    if failure == "partial":
        assert db.get(GeneratedMock, source.id).status == "bank_only"
        assert len(bank.assemble(db, 1, PLAN, MAJORS, allow_partial=True)) == 1


def test_stale_empty_ranked_match_ends_instead_of_waiting_forever(db):
    from datetime import datetime, timedelta
    source = make_mock(db, owner=1, status="claimed")
    source.questions = "[]"
    match = ArenaMatch(student_a_id=1, student_b_id=2, mock_id=source.id, status="pending",
        created_at=datetime.utcnow()-timedelta(minutes=16))
    db.add(match); db.commit()
    result = arena.get_match(match.id, db.get(User, 1), db)
    assert result["status"] == "cancelled" and result["generation_error"]
    assert db.get(User, 1).rating == 1000


def test_ranked_does_not_queue_or_charge_when_no_shared_verified_questions_and_provider_blocked(db, monkeypatch):
    from app.auth.database import ArenaQueueEntry
    make_mock(db, owner=1, status="claimed")  # Private practice is not ranked stock.
    monkeypatch.setattr(arena, "pool_quota_status", lambda: {"blocked":True})
    monkeypatch.setattr(arena, "consume_ai_use", lambda *a: pytest.fail("Do not charge a refused join"))
    monkeypatch.setattr(arena, "require_pool_available", lambda: (_ for _ in ()).throw(HTTPException(503, detail="quota")))
    with pytest.raises(HTTPException) as error:
        arena.join_queue(arena.JoinPayload(), db.get(User, 1), db)
    assert error.value.status_code==503
    assert db.query(ArenaQueueEntry).count()==0 and db.query(ArenaMatch).count()==0


def test_ranked_prefers_unused_booklets_then_reuses_existing_questions(db, monkeypatch):
    plan = mock_generation.scale_plan(mock_generation.default_plan("riazi"), divisor=3, minimum=3)
    def full(label):
        row = make_mock(db, label=label, difficulty="duel")
        questions = [{"_id": i + 1, "subject": s["name"], "text": f"{label} {s['name']} {i}",
            "topic": "", "options": ["a", "b", "c", "d"], "answer": 1,
            "verification_status": "verified"} for s in plan for i in range(s["questions"])]
        # ids must be unique across the exam, irrespective of subject.
        for i, q in enumerate(questions): q["_id"] = i + 1
        row.questions = json.dumps(questions); row.bank_indexed = False
        bank.index_mock(db, row); db.commit()
        return row
    old = full("used")
    old.status = "claimed"; old.student_id = 1
    bank.mark_used(db, bank.active_questions(db, old)); db.commit()
    fresh = full("fresh")
    chosen = pool_core.claim_duel_booklet(db, 1, 2, "riazi")
    db.commit()
    assert chosen.id == fresh.id
    fallback = pool_core.claim_duel_booklet(db, 1, 2, "riazi")
    db.commit()
    assert fallback is not None and fallback.id not in (fresh.id, old.id)
    assert all(q["verification_status"] == "verified" for q in json.loads(fallback.questions))
    assert db.get(GeneratedMock, old.id).student_id == 1


def test_bank_filters_grade_topics_and_unverified_answers(db):
    make_mock(db, grade="دوازدهم")
    assert bank.assemble(db, 1, PLAN, MAJORS, grade="دهم") == []
    assert bank.assemble(db, 1, PLAN, MAJORS, topics=["انتگرال"]) == []
    q = db.query(BankQuestion).first(); q.verified = False; db.commit()
    selected = bank.assemble(db, 1, PLAN, MAJORS)
    assert len(selected) == 2 and q.id not in {r["bank_id"] for r in selected}


def test_admin_stock_and_deficits_do_not_count_unverified_or_reported_booklets(db):
    make_mock(db, verified=False, label="legacy")
    good = make_mock(db, label="verified")
    shelf = next(s for s in pool_core.pool_levels(db) if s['major_key']=='riazi' and s['difficulty']=='konkur')
    assert shelf['available']==1 and shelf['needs_review']==1
    assert pool_core.pool_deficit(db, 'riazi', 'konkur', 2)==1
    bank.record_report(db, good, 1, 1, 'incorrect verified answer')
    assert pool_core.ready_count(db, difficulty='konkur')==0
    assert db.get(GeneratedMock, good.id) is not None


def test_admin_correction_keeps_original_and_creates_fresh_verified_revision(db):
    source = make_mock(db, owner=1, status="claimed")
    reported = bank.record_report(db, source, 1, 1, "the answer is wrong")
    result = admin.review_question(reported["question_id"], admin.QuestionReviewIn(
        action="correct", answer=2, note="Independently solved; option 3 is correct"), db)
    old = db.get(BankQuestion, reported["question_id"])
    new = db.get(BankQuestion, result["replacement_id"])
    assert old.status == "deleted" and json.loads(old.content)["answer"] == 1
    assert new.status == "active" and new.verified and new.uses == 0
    assert json.loads(new.content)["answer"] == 2
    assert db.query(QuestionReport).count() == 1
    assert len(json.loads(source.questions)) == 3


def test_deleted_question_cannot_be_restored_or_reported_back_into_use(db):
    source = make_mock(db, owner=1, status="claimed")
    report = bank.record_report(db, source, 1, 1, "the answer is wrong")
    admin.review_question(report["question_id"], admin.QuestionReviewIn(action="delete"), db)
    with pytest.raises(HTTPException):
        admin.review_question(report["question_id"], admin.QuestionReviewIn(action="restore"), db)
    bank.record_report(db, source, 1, 1, "still incorrect")
    assert db.get(BankQuestion, report["question_id"]).status != "active"


def test_non_admin_cannot_read_answer_keys_or_review_reports(db):
    app = FastAPI(); app.include_router(admin.router); app.include_router(mocks.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    client = TestClient(app)
    assert client.get("/api/admin/questions/corrupt").status_code == 403
    assert client.post("/api/admin/questions/1/review", json={"action": "restore"}).status_code == 403


def test_targeted_run_ignores_previous_inventory_and_only_builds_requested_kind(monkeypatch):
    calls = []
    pool_core.begin_progress("test")
    monkeypatch.setattr(pool_core, "generate_one", lambda db, major, difficulty: calls.append((major, difficulty)) or True)
    monkeypatch.setattr(pool_core, "generate_one_duel", lambda *a, **k: pytest.fail("Must not generate ranked"))
    monkeypatch.setattr(pool_core, "pool_quota_status", lambda: {"blocked": False})
    assert pool_core.generate_selected(None, majors=["tajrobi"], difficulties=["hard"], count=3) == 3
    assert calls == [("tajrobi", "hard")] * 3


def test_continuous_selected_run_stops_on_cancel_and_keeps_completed_work(monkeypatch):
    calls = []
    pool_core.begin_progress("test")
    monkeypatch.setattr(pool_core, "pool_quota_status", lambda: {"blocked": False})
    def produce(*args):
        calls.append(1)
        if len(calls) == 4: pool_core.request_cancel()
        return True
    monkeypatch.setattr(pool_core, "generate_one_duel", produce)
    assert pool_core.generate_selected(None, kind="ranked", majors=["riazi"], count=0) == 4
    assert pool_core.progress_snapshot()["produced"] == 4


def test_partial_verified_generation_is_saved_even_when_booklet_is_rejected(db, monkeypatch):
    tiny = [{"_id": 1, "subject": "ریاضی", "text": "verified survivor", "topic": "تابع",
        "options": ["a", "b", "c", "d"], "answer": 1, "verification_status": "verified"}]
    monkeypatch.setattr(mock_generation, "generate_booklet", lambda *a, **k: tiny)
    monkeypatch.setattr(mock_generation, "verify_and_repair_booklet", lambda *a, **k: tiny)
    assert not pool_core.generate_one(db, "riazi", "konkur")
    assert db.query(BankQuestion).filter(BankQuestion.verified == True).count() == 1
    assert db.query(GeneratedMock).filter(GeneratedMock.status == "pending_use").count() == 0


def test_live_ranked_quarantine_cancels_game_without_elo_changes(db):
    source = make_mock(db, owner=1, status="claimed")
    match = ArenaMatch(student_a_id=1, student_b_id=2, mock_id=source.id, status="pending", elo_a=1000, elo_b=1000)
    db.add(match); db.commit()
    bank.record_report(db, source, 1, 1, "the answer is wrong")
    with pytest.raises(HTTPException) as e:
        arena.submit(match.id, mocks.SubmitPayload(answers={"2": 1}), db.get(User, 2), db)
    assert e.value.status_code == 409
    db.refresh(match)
    assert match.status == "cancelled" and match.delta_a == match.delta_b == 0
    assert db.get(User, 1).rating == db.get(User, 2).rating == 1000


def test_authored_assessment_reports_and_corrections_affect_future_sessions(db):
    from app.rag.assessment_bank import create_assessment
    original = create_assessment(db, 1, "calculus")
    first = original["questions"][0]
    result = mocks.report_question(original["mock_id"], first["id"],
        mocks.QuestionReportIn(reason="explanation of limit is incorrect"), db.get(User, 1), db)
    later = create_assessment(db, 2, "calculus")
    assert len(later["questions"]) == len(original["questions"]) - 1
    assert first["question"] not in {q["question"] for q in later["questions"]}
    correction = admin.review_question(result["question_id"], admin.QuestionReviewIn(action="correct",
        text=first["question"] + " (corrected)", answer=first["answer"], note="Reviewed wording"), db)
    newest = create_assessment(db, 2, "calculus")
    assert len(newest["questions"]) == len(original["questions"])
    assert any(q["question"].endswith("(corrected)") for q in newest["questions"])
    assert db.get(BankQuestion, correction["replacement_id"]).difficulty == "assessment"
    assert bank.assemble(db, 2, PLAN, MAJORS) == []  # Static answers never enter ranked.


def test_calculus_assessment_uses_current_book_topics_instead_of_legacy_integrals(db):
    from app.rag.assessment_bank import create_assessment
    from pathlib import Path
    source = json.loads((Path(__file__).resolve().parents[1] / "frontend/src/assessmentQuestions.json").read_text(encoding="utf-8"))[0]
    unchanged = source["questions"][0]
    # An old authored archive remains in history, but cannot join the new source version.
    old = GeneratedMock(student_id=0, title="old-assessment", major="assessment:calculus",
        difficulty="assessment", status="bank_only", bank_scope="shared", questions=json.dumps([
            {"_id":1,"subject":"حسابان","topic":"انتگرال معین","text":"انتگرال قدیمی",
             "options":["0","1","2","3"],"answer":1,"verification_status":"verified"},
            {"_id":2,"subject":"حسابان","topic":"calculus","text":unchanged["question"],
             "options":unchanged["options"],"answer":unchanged["answer"],"verification_status":"verified"}]))
    db.add(old); db.flush(); bank.index_mock(db, old); db.commit()
    current = create_assessment(db, 1, "calculus")
    assert len(current["questions"]) == 10
    assert all("انتگرال" not in q["question"] and "∫" not in q["question"] for q in current["questions"])
    assert "abolished" not in json.dumps(current)
    questions = json.loads(db.get(GeneratedMock, current["mock_id"]).questions)
    assert all(q["topic"] and q["topic"] != "calculus" for q in questions)
    assert db.get(GeneratedMock, old.id) is not None


def test_upgrade_creates_bank_and_flags_without_replacing_existing_accounts_or_mocks(tmp_path, monkeypatch):
    from app.auth import database
    from sqlalchemy import text
    engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    # Retain the real current user table but emulate the previous mock schema.
    User.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, username, hashed_password) VALUES (1, 'keep-account', 'keep-hash')"))
        conn.execute(text("CREATE TABLE generated_mocks (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, title VARCHAR NOT NULL, major VARCHAR, grade VARCHAR, duration_minutes INTEGER NOT NULL, questions TEXT NOT NULL, status VARCHAR DEFAULT 'claimed', difficulty VARCHAR DEFAULT '', created_at DATETIME)"))
        conn.execute(text("INSERT INTO generated_mocks (id,student_id,title,duration_minutes,questions) VALUES (1,1,'keep-exam',10,'[]')"))
    monkeypatch.setattr(database, "engine", engine)
    database.ensure_schema()
    with Session(engine) as session:
        user = session.get(User, 1); exam = session.get(GeneratedMock, 1)
        assert (user.username, user.hashed_password) == ('keep-account', 'keep-hash')
        assert exam.questions == '[]' and exam.title == 'keep-exam'
        assert exam.bank_scope == 'private' and not exam.bank_indexed
        assert session.query(BankQuestion).count() == 0
    engine.dispose()
