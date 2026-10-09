"""Persistent selected production, honest stock, and immediate empty responses."""
import json
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.rag import pool_service as service, pool_core, knowledge_base
from app.routers import admin, mocks, arena


@pytest.fixture(autouse=True)
def worker(monkeypatch):
    pool_core.finish_progress(); pool_core.clear_cancel()
    monkeypatch.setattr(service, 'SessionLocal', lambda: nullcontext(SimpleNamespace()))
    monkeypatch.setattr(service, 'pool_quota_status', lambda: {'blocked':False})
    monkeypatch.setattr(pool_core, 'assemble_stock', lambda *a, **kw: False)
    monkeypatch.setattr(service, 'resume', lambda: None)
    yield
    pool_core.finish_progress(); pool_core.clear_cancel()


def config(**values):
    return dict(kind='mock', majors=['riazi'], difficulties=['konkur'], grade='دهم',
        count=1, total_questions=5, subjects=[], topics=['تابع'], **values)


def test_saved_selection_survives_restart_and_produces_requested_format(monkeypatch):
    captured=[]
    service.start(config())
    assert service.snapshot()['enabled']
    # The process loses its thread/progress, not the saved job.
    def produce(db, major, difficulty, **kwargs):
        captured.append((major,difficulty,kwargs)); return True
    monkeypatch.setattr(pool_core, 'generate_one', produce)
    service._run()
    assert captured==[('riazi','konkur',{'grade':'دهم','subjects':[], 'topics':['تابع'],'total_questions':5})]
    state=service.snapshot()
    assert state['status']=='finished' and state['produced']==1 and not state['enabled']


def test_continuous_run_has_no_five_booklet_ceiling_and_preserves_cancel(monkeypatch):
    cfg=config(); cfg['count']=0
    calls=[]
    def produce(*a, **kw):
        calls.append(1)
        if len(calls)==7: service.cancel()
        return True
    monkeypatch.setattr(pool_core, 'generate_one', produce)
    service.start(cfg); service._run()
    assert len(calls)==7 and service.snapshot()['produced']==7
    assert service.snapshot()['status']=='stopped' and not service.snapshot()['enabled']


def test_daily_quota_waits_without_provider_calls_and_resumes(monkeypatch):
    health=[{'blocked':True,'code':'provider_daily_quota','message':'quota reset pending',
        'retry_at':'2026-10-08T07:00:00Z','retry_after':500}, {'blocked':False}]
    monkeypatch.setattr(service, 'pool_quota_status', lambda: health[0])
    waits=[]; calls=[]
    def wait(seconds):
        assert not calls and service.snapshot()['status']=='waiting_for_quota'
        waits.append(seconds); health.pop(0); return False
    monkeypatch.setattr(service._wake, 'wait', wait)
    monkeypatch.setattr(pool_core, 'generate_one', lambda *a, **kw: calls.append(1) or True)
    service.start(config()); service._run()
    assert waits==[60] and calls==[1] and service.snapshot()['status']=='finished'


def test_access_denial_requires_changed_credentials_not_repeated_probes(monkeypatch):
    monkeypatch.setattr(service, 'pool_quota_status', lambda: {'blocked':True,'message':'access denied'})
    monkeypatch.setattr(pool_core, 'generate_one', lambda *a, **kw: pytest.fail('No access probes'))
    service.start(config()); service._run()
    assert service.snapshot()['status']=='failed' and not service.snapshot()['enabled']


def test_verified_bank_stock_finishes_during_quota_pause_without_drafting(monkeypatch):
    monkeypatch.setattr(service, 'pool_quota_status', lambda: {'blocked':True,
        'message':'daily quota', 'retry_at':'2026-10-10T00:00:00Z'})
    monkeypatch.setattr(pool_core, 'generate_one', lambda *a, **kw: pytest.fail('No drafting'))
    stock=[]
    monkeypatch.setattr(pool_core, 'assemble_stock', lambda *a, **kw: stock.append(kw) or True)
    service.start(config()); service._run()
    assert len(stock)==1 and stock[0]['total_questions']==5
    assert service.snapshot()['status']=='finished' and service.snapshot()['produced']==1


def test_both_rotates_mock_and_exact_ranked_shapes(monkeypatch):
    cfg=config(); cfg.update(kind='both',count=4)
    calls=[]
    monkeypatch.setattr(pool_core, 'generate_one', lambda *a, **kw: calls.append('mock') or True)
    monkeypatch.setattr(pool_core, 'generate_one_duel', lambda *a, **kw: calls.append('ranked') or True)
    service.start(cfg); service._run()
    assert calls==['mock','ranked','mock','ranked']
    for major in pool_core.POOL_MAJORS:
        label=pool_core.CANONICAL_MAJOR[major]
        assert pool_core.generation_plan(major, ranked=True)==knowledge_base.pair_plan(label,label)['plan']


def test_invalid_major_subject_selection_is_rejected_before_start(monkeypatch):
    monkeypatch.setattr(service, 'start', lambda *a: pytest.fail('Invalid selection'))
    with pytest.raises(HTTPException) as error:
        admin.pool_restock(None, admin.PoolRunIn(major='riazi',subjects=['زیست‌شناسی']))
    assert error.value.status_code==422


def test_failed_launch_restores_previous_state(monkeypatch):
    def fail(): raise RuntimeError('thread refused')
    monkeypatch.setattr(service, 'resume', fail)
    with pytest.raises(RuntimeError): service.start(config())
    assert not service.snapshot()['enabled']
