"""Partial verified inventory becomes real booklets, without duplicate stock."""
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.auth.database import Base, GeneratedMock, BankQuestion
from app.rag import pool_core as pool, mock_generation as mg, question_bank as bank


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def question(subject, n):
    return dict(subject=subject, topic='تابع', text=f'{subject} سوال شماره {n}',
        options=['a','b','c','d'], answer=0, verification_status='verified')


def archive(db, questions, *, status='bank_only', owner=0, grade='دوازدهم'):
    mock = GeneratedMock(student_id=owner, title='stock', major=pool.CANONICAL_MAJOR['riazi'],
        grade=grade, difficulty='konkur', duration_minutes=10,
        questions=json.dumps(questions), status=status, bank_scope='shared' if owner==0 else 'private')
    db.add(mock); db.flush(); bank.index_mock(db, mock); db.commit()
    return mock


def test_bank_assembles_complete_mock_once_without_model_calls(db, monkeypatch):
    plan = pool.generation_plan('riazi', total_questions=10)
    archive(db, [question(row['name'], n) for row in plan for n in range(row['questions'])])
    monkeypatch.setattr(mg, 'generate_booklet', lambda *a, **kw: pytest.fail('No model'))
    monkeypatch.setattr(mg, 'verify_and_repair_booklet', lambda *a, **kw: pytest.fail('Already verified'))
    assert pool.assemble_stock(db, 'riazi', 'konkur', total_questions=10)
    first=db.query(GeneratedMock).filter_by(status='pending_use').one()
    rows=json.loads(first.questions)
    assert len(rows)==10 and len({q['bank_id'] for q in rows})==10
    assert not pool.assemble_stock(db, 'riazi', 'konkur', total_questions=10)
    assert db.query(GeneratedMock).filter_by(status='pending_use').count()==1


def test_drafts_only_subject_deficits_and_verifies_only_new_questions(db, monkeypatch):
    plan = pool.generation_plan('riazi', total_questions=10)
    # All but two questions of the final subject already exist.
    archive(db, [question(row['name'], n) for row in plan
                 for n in range(row['questions'] - (2 if row==plan[-1] else 0))])
    calls=[]; verified=[]
    def draft(user, missing, **kw):
        calls.extend(missing)
        return [question(row['name'], n+100) for row in missing for n in range(row['questions'])]
    def solve(questions, *a, **kw):
        verified.extend(questions); return questions
    monkeypatch.setattr(mg, 'generate_booklet', draft)
    monkeypatch.setattr(mg, 'verify_and_repair_booklet', solve)
    assert pool.generate_one(db, 'riazi', 'konkur', total_questions=10)
    assert [(r['name'],r['questions']) for r in calls]==[(plan[-1]['name'],2)]
    assert len(verified)==2
    mock=db.query(GeneratedMock).filter_by(status='pending_use').one()
    assert len(json.loads(mock.questions))==10
    assert db.query(BankQuestion).filter_by(verified=True).count()==10


def test_seed_selection_excludes_reported_private_used_older_grade_and_reserved(db):
    rows=[question('ریاضی', n) for n in range(6)]
    archive(db, rows)
    archive(db, [question('ریاضی',99)], owner=7)
    records=db.query(BankQuestion).filter_by(owner_id=0).order_by(BankQuestion.id).all()
    records[0].status='corrupt'; records[1].verified=False; records[2].uses=1
    records[3].grade_level=12; records[4].grade_level=10; records[5].grade_level=10
    db.commit()
    archive(db, [{**rows[4], 'bank_id':records[4].id}], status='pending_use', grade='دهم')
    selected=pool._stock_seeds(db,'riazi','konkur',[{'name':'ریاضی','questions':10,'minutes':10}], 'دهم', ['تابع'])
    assert [q['bank_id'] for q in selected]==[records[5].id]
    assert pool._stock_seeds(db,'riazi','konkur',[{'name':'ریاضی','questions':10,'minutes':10}], 'دهم', ['هندسه'])==[]


def test_partial_stock_is_not_misrepresented_as_complete_during_quota(db, monkeypatch):
    archive(db, [question('ریاضی',1)])
    monkeypatch.setattr(mg, 'generate_booklet', lambda *a, **kw: pytest.fail('Quota means no API calls'))
    assert not pool.assemble_stock(db,'riazi','konkur',total_questions=10)
    assert db.query(GeneratedMock).filter_by(status='pending_use').count()==0


def test_ranked_and_practice_cannot_reserve_the_same_stock(db, monkeypatch):
    monkeypatch.setattr(pool,'generation_plan', lambda *a, **kw: [{'name':'ریاضی','questions':3,'minutes':30}])
    archive(db,[question('ریاضی',n) for n in range(3)])
    monkeypatch.setattr(mg,'generate_booklet', lambda *a, **kw: pytest.fail('No API'))
    assert pool.assemble_stock(db,'riazi',pool.DUEL_DIFFICULTY)
    assert not pool.assemble_stock(db,'riazi','konkur')


@pytest.mark.parametrize('blocked', ['reserved', 'reported', 'used'])
def test_regenerated_old_question_cannot_reenter_fresh_stock(db, monkeypatch, blocked):
    plan=[{'name':'ریاضی','questions':3,'minutes':30}]
    monkeypatch.setattr(pool,'generation_plan',lambda *a,**kw: plan)
    questions=[question('ریاضی',n) for n in range(3)]
    old=archive(db,questions,status='pending_use' if blocked=='reserved' else 'bank_only')
    if blocked!='reserved':
        for row in db.query(BankQuestion):
            if blocked=='reported': row.status='corrupt'
            else: row.uses=1
        db.commit()
    monkeypatch.setattr(mg,'generate_booklet', lambda *a,**kw: [dict(q) for q in questions])
    monkeypatch.setattr(mg,'verify_and_repair_booklet', lambda rows,*a,**kw: rows)
    assert not pool.generate_one(db,'riazi','konkur')
    assert db.query(GeneratedMock).filter_by(status='pending_use').count()==(blocked=='reserved')
