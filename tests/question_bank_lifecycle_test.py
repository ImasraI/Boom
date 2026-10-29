"""Local-only historical-attempt regressions; temporary SQLite, no providers."""
import json
import pytest
from sqlalchemy import create_engine,inspect,text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth.database import Base,User,GeneratedMock,MockAttempt,WrongAnswer,BankQuestion
from app.rag import question_bank as bank
from app.routers import mocks
from fastapi import HTTPException


@pytest.fixture
def example():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user=User(id=1,username='synthetic-lifecycle',hashed_password='not-a-password')
        db.add(user);db.flush()
        qs=[dict(_id=i,subject='ریاضی',topic='synthetic',text=f'Synthetic question {i}',
            options=['1','2','3','4'],answer=1,explanation='Synthetic explanation',verification_status='verified')
            for i in (1,2)]
        row=GeneratedMock(student_id=1,title='Synthetic lifecycle',major='ریاضی فیزیک',grade='دوازدهم',
            duration_minutes=10,questions=json.dumps(qs),status='claimed',difficulty='konkur',bank_scope='private')
        db.add(row);db.flush();bank.index_mock(db,row);db.commit()
        yield db,user,row
    engine.dispose()


def submit(db,user,row):
    return mocks.submit_mock(row.id,mocks.SubmitPayload(answers={'1':1,'2':0}),user,db)


def test_retry_after_report_replays_the_original_result_not_current_bank(example):
    db,user,row=example
    first=submit(db,user,row)
    misses=db.query(WrongAnswer).count()
    bank.record_report(db,row,user.id,2,'Synthetic invalid question report')
    retry=submit(db,user,row)
    assert retry==first
    assert db.query(MockAttempt).count()==1 and db.query(WrongAnswer).count()==misses
    assert len(bank.active_questions(db,row))==1
    assert mocks.history(user,db)[0]['score']==first['score']


def test_retry_still_succeeds_after_all_questions_are_retired(example):
    db,user,row=example;first=submit(db,user,row)
    for number in (1,2):bank.record_report(db,row,user.id,number,'Synthetic retired question')
    assert submit(db,user,row)==first


def test_restoring_a_previously_excluded_item_does_not_change_completed_attempt(example):
    db,user,row=example
    reported=bank.record_report(db,row,user.id,2,'Synthetic excluded before submission')
    first=submit(db,user,row)
    assert first['correct']==1 and first['wrong']==0
    db.get(BankQuestion,reported['question_id']).status='active';db.commit()
    assert submit(db,user,row)==first


def test_legacy_completed_attempt_uses_immutable_booklet_and_stored_totals(example):
    db,user,row=example;first=submit(db,user,row)
    db.query(MockAttempt).one().result_snapshot=None;db.commit()
    bank.record_report(db,row,user.id,2,'Synthetic later quarantine')
    assert submit(db,user,row)==first


def test_legacy_unknown_scored_subset_keeps_totals_without_inventing_review(example):
    db,user,row=example
    bank.record_report(db,row,user.id,2,'Synthetic excluded before attempt')
    first=submit(db,user,row)
    db.query(MockAttempt).one().result_snapshot=None;db.commit()
    retry=submit(db,user,row)
    for field in ('score','raw_score','correct','wrong','blank'):
        assert retry[field]==first[field]
    assert retry['historical_review_incomplete'] is True
    assert retry['review']==[] and retry['subjects']==[]


def test_invalid_snapshot_cannot_override_persisted_attempt_metrics(example):
    db,user,row=example;first=submit(db,user,row)
    attempt=db.query(MockAttempt).one();snapshot=json.loads(attempt.result_snapshot)
    snapshot['response']['score']=999;attempt.result_snapshot=json.dumps(snapshot);db.commit()
    bank.record_report(db,row,user.id,2,'Synthetic later quarantine')
    assert submit(db,user,row)==first


def test_completed_snapshot_does_not_bypass_submission_authorization(example):
    db,user,row=example;submit(db,user,row)
    other=User(id=2,username='synthetic-other',hashed_password='not-a-password');db.add(other);db.commit()
    with pytest.raises(HTTPException) as error:
        mocks.submit_mock(row.id,mocks.SubmitPayload(answers={}),other,db)
    assert error.value.status_code==404


def test_history_reopens_original_answers_without_resubmission_or_new_weaknesses(example):
    db,user,row=example;first=submit(db,user,row)
    wrong_before=db.query(WrongAnswer).count()
    bank.record_report(db,row,user.id,2,'Synthetic later quarantine')
    saved=mocks.get_attempt(first['attempt_id'],user,db)
    assert saved=={'mock_id':row.id,'title':row.title,'result':first}
    assert db.query(MockAttempt).count()==1
    assert db.query(WrongAnswer).count()==wrong_before
    assert mocks.history(user,db)[0]['title']==row.title


def test_history_detail_is_private_even_when_booklet_is_shared(example):
    db,user,row=example;first=submit(db,user,row)
    other=User(id=2,username='synthetic-other',hashed_password='not-a-password')
    db.add(other);db.commit()
    with pytest.raises(HTTPException) as error:
        mocks.get_attempt(first['attempt_id'],other,db)
    assert error.value.status_code==404
    assert mocks.history(other,db)==[]
    with pytest.raises(HTTPException) as missing:
        mocks.get_attempt(999999,user,db)
    assert missing.value.status_code==404


def test_history_detail_marks_unrecoverable_legacy_review(example):
    db,user,row=example
    bank.record_report(db,row,user.id,2,'Synthetic excluded before attempt')
    first=submit(db,user,row)
    db.query(MockAttempt).one().result_snapshot=None;db.commit()
    response=mocks.get_attempt(first['attempt_id'],user,db)['result']
    assert response['score']==first['score']
    assert response['historical_review_incomplete'] is True
    assert response['review']==[]


def test_history_http_paths_and_read_authorization(example):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    db,user,row=example;first=submit(db,user,row)
    app=FastAPI();app.include_router(mocks.router)
    app.dependency_overrides[mocks.get_db]=lambda: db
    with TestClient(app) as client:
        assert client.get('/api/mocks/history').status_code==401
        assert client.get(f"/api/mocks/attempts/{first['attempt_id']}").status_code==401
        app.dependency_overrides[mocks.get_current_user]=lambda: user
        assert client.get('/api/mocks/history').json()[0]['title']==row.title
        response=client.get(f"/api/mocks/attempts/{first['attempt_id']}")
        assert response.status_code==200 and response.json()['result']==first
        assert client.get('/api/mocks/history?offset=-1').status_code==422
        assert client.get('/api/mocks/history?offset=20').json()==[]
        app.dependency_overrides[mocks.get_current_user]=lambda: User(id=99,username='synthetic-private')
        assert client.get(f"/api/mocks/attempts/{first['attempt_id']}").status_code==404
        assert client.get('/api/mocks/history').json()==[]


def test_upgrade_adds_nullable_snapshot_without_replacing_legacy_attempt(tmp_path,monkeypatch):
    from app.auth import database
    engine=create_engine('sqlite:///'+(tmp_path/'legacy.db').as_posix())
    try:
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE mock_attempts (id INTEGER PRIMARY KEY,mock_id INTEGER,student_id INTEGER,answers TEXT,duration_seconds INTEGER,score FLOAT,correct INTEGER,wrong INTEGER,blank INTEGER,created_at DATETIME)'))
            connection.execute(text("INSERT INTO mock_attempts(id,mock_id,student_id,answers,score,correct,wrong,blank) VALUES(9,1,1,'{}',33.3,1,1,0)"))
        monkeypatch.setattr(database,'engine',engine)
        database.ensure_schema()
        assert 'result_snapshot' in {c['name'] for c in inspect(engine).get_columns('mock_attempts')}
        with engine.connect() as connection:
            saved=connection.execute(text('SELECT id,score,correct,wrong,result_snapshot FROM mock_attempts')).one()
            assert tuple(saved)==(9,33.3,1,1,None)
    finally:engine.dispose()
