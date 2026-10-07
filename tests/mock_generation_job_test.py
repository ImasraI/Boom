"""Long mock generation must not hold an HTTP request or cross accounts."""
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import Base, User
from app.auth.deps import get_current_user
from app.rag import mock_jobs
from app.routers import mocks


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(User(id=7,username='job-test',phone='09129990001',hashed_password='test-only'))
        db.commit()
    monkeypatch.setattr(mocks,'SessionLocal',sessions)
    charges=[]; refunds=[]; workers=[]
    monkeypatch.setattr(mocks,'consume_ai_use',lambda uid,feature:charges.append((uid,feature)))
    monkeypatch.setattr(mocks,'release_ai_use',lambda uid,feature:refunds.append((uid,feature)))
    class DeferredThread:
        def __init__(self,target,args,**kwargs):
            self.target=target; self.args=args
        def start(self):
            workers.append(self)
    monkeypatch.setattr(mocks,'Thread',DeferredThread)
    actor=SimpleNamespace(id=7)
    app=FastAPI(); app.include_router(mocks.router)
    app.dependency_overrides[get_current_user]=lambda:actor
    mock_jobs._JOBS.clear()
    yield TestClient(app),actor,charges,refunds,workers
    mock_jobs._JOBS.clear()
    engine.dispose()


def test_slow_generation_returns_immediately_and_duplicate_clicks_resume(setup,monkeypatch):
    client,actor,charges,refunds,workers=setup
    calls=[]
    monkeypatch.setattr(mocks,'_generate_reserved_mock',lambda cfg,user,db:
        calls.append(user.id) or {'mock_id':123,'total_questions':3,'source':'question_bank'})
    started=client.post('/api/mocks/generation',json={'mode':'practice'})
    assert started.status_code==202 and not calls
    job=started.json()
    again=client.post('/api/mocks/generation',json={'mode':'practice'})
    assert again.json()==job and len(workers)==1 and len(charges)==1
    assert client.get('/api/mocks/generation/'+job['job_id']).json()['status']=='running'
    workers[0].target(*workers[0].args)
    ready=client.get('/api/mocks/generation/'+job['job_id']).json()
    assert ready['status']=='ready' and ready['result']['mock_id']==123
    assert calls==[7] and not refunds


def test_other_account_cannot_read_or_resume_a_job(setup):
    client,actor,charges,refunds,workers=setup
    first=client.post('/api/mocks/generation',json={}).json()['job_id']
    actor.id=8
    assert client.get('/api/mocks/generation/'+first).status_code==404
    second=client.post('/api/mocks/generation',json={}).json()['job_id']
    assert first!=second and len(workers)==2


def test_provider_error_refunds_once_and_preserves_retry_details(setup,monkeypatch):
    client,actor,charges,refunds,workers=setup
    def blocked(*args):
        raise HTTPException(503,{'code':'provider_daily_quota','message':'quota reset pending'},
                            headers={'Retry-After':'600'})
    monkeypatch.setattr(mocks,'_generate_reserved_mock',blocked)
    job=client.post('/api/mocks/generation',json={}).json()['job_id']
    workers[0].target(*workers[0].args)
    response=client.get('/api/mocks/generation/'+job)
    assert response.status_code==503 and response.headers['Retry-After']=='600'
    assert response.json()['detail']['code']=='provider_daily_quota'
    client.get('/api/mocks/generation/'+job)
    assert refunds==[(7,'mock_generate')] and len(charges)==1


def test_failed_thread_start_releases_quota_and_does_not_leave_an_active_job(setup,monkeypatch):
    client,actor,charges,refunds,workers=setup
    def broken_start(*args,**kwargs):
        raise RuntimeError('thread failed')
    monkeypatch.setattr(mocks,'Thread',broken_start)
    with pytest.raises(RuntimeError):
        client.post('/api/mocks/generation',json={})
    assert not mock_jobs._JOBS and refunds==[(7,'mock_generate')]


def test_job_capacity_and_completed_result_expiry(setup,monkeypatch):
    client,actor,charges,refunds,workers=setup
    jobs=[mock_jobs.reserve(uid)[0] for uid in (7,8,9)]
    with pytest.raises(HTTPException) as exc:
        mock_jobs.reserve(10)
    assert exc.value.status_code==503
    mock_jobs.finish(jobs[0]['job_id'],result={'mock_id':12})
    now=mock_jobs.time.monotonic()
    monkeypatch.setattr(mock_jobs.time,'monotonic',lambda:now+7201)
    mock_jobs.reserve(10)
    with pytest.raises(HTTPException) as exc:
        mock_jobs.get(jobs[0]['job_id'],7)
    assert exc.value.status_code==404
