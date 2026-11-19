import json
from types import SimpleNamespace
from app.rag import current_maze_stock as stock


def test_current_counts_exclude_historical_and_unverified_booklets(monkeypatch):
    plan = [{'name':'ریاضی','questions':10,'weekly_ranked_scope':'current'}]
    monkeypatch.setattr(stock.weekly_ranked,'preview',lambda:dict(available=True,date='2030-01-10',scope='current',plan=plan))
    def booklet(scope, verified=True):
        return SimpleNamespace(questions=json.dumps([dict(subject='ریاضی',weekly_ranked_scope=scope,verification_status='verified' if verified else 'draft') for _ in range(10)]))
    rows=[booklet('current'),booklet('older'),booklet('current',False)]
    monkeypatch.setattr(stock.pool_core,'_ready_stock',lambda db,raw:all(q['verification_status']=='verified' for q in json.loads(raw)))
    db=SimpleNamespace(scalars=lambda query:rows)
    result=stock.inventory(db)
    assert sum(r['ready_booklets'] for r in result)==1
    assert len(result)==6
    assert sum(r['mapping_ready'] for r in result)==1


def test_missing_scope_mapping_never_promotes_general_stock(monkeypatch):
    monkeypatch.setattr(stock.weekly_ranked,'preview',lambda:dict(available=False,date='2030-01-10',scope='held',code='maze_topics_unmapped'))
    def forbidden(query): raise AssertionError('Unmapped scope must not count generic stock')
    result=stock.inventory(SimpleNamespace(scalars=forbidden))
    assert all(r['ready_booklets']==0 and not r['mapping_ready'] for r in result)
