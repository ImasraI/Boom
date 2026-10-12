"""Offline recovery regressions for partial weekly drafts and usable stock."""
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import Base, BankQuestion, GeneratedMock, PoolDraftJob
from app.config import Settings
from app.rag import exam_blueprint as bp, pool_core, pool_queue as queue, pool_service, question_bank, weekly_ranked


SCOPE = 'current-reviewed-maze-scope'
NODES = [
    dict(id='geometry', subject='هندسه', title='قضیه تالس'),
    dict(id='discrete', subject='ریاضیات گسسته', title='نظریه اعداد'),
    dict(id='calculus-10', subject='حسابان', title='تابع دهم'),
    dict(id='calculus-12', subject='حسابان', title='تابع دوازدهم'),
    dict(id='physics-10', subject='فیزیک', title='ویژگی‌های فیزیکی مواد'),
    dict(id='physics-12', subject='فیزیک', title='حرکت بر خط راست'),
    dict(id='chemistry-10', subject='شیمی', title='کیهان'),
    dict(id='chemistry-12', subject='شیمی', title='مولکول‌ها'),
]
NODES = [{**n, 'year':12, 'majors':['riazi'], 'sources':[dict(book='source',page=1,quote=n['title'])]} for n in NODES]


def plan():
    out = []
    for subject, count, ids in (
        ('ریاضی',4,['geometry','discrete','calculus-10','calculus-12']),
        ('فیزیک',3,['physics-10','physics-12']),
        ('شیمی',3,['chemistry-10','chemistry-12']),
    ):
        out.append(dict(name=subject,questions=count,major='riazi',full_mock=True,book_grounded=True,
            curriculum_ids=ids, weekly_ranked_scope=SCOPE,
            maze_scope={cid:['reviewed bounds ' + cid] for cid in ids},
            **({'branches':dict(geometry=1,discrete=1,calculus=2)} if subject=='ریاضی' else {})))
    return out


def config(count=0):
    return dict(kind='weekly_ranked',majors=['riazi'],difficulties=['konkur'],grade='دوازدهم',
                count=count,total_questions=10,subjects=[],topics=[],weekly_scope=SCOPE,weekly_plan=plan())


def question(cid, serial=0, **extra):
    node = next(n for n in NODES if n['id']==cid)
    subject = node['subject'] if cid.startswith(('physics','chemistry')) else 'ریاضی'
    return dict(subject=subject,curriculum_id=cid,branch=bp.math_branch(node['subject'],node['title']),
        weekly_ranked_scope=SCOPE, maze_scope=['untrusted model bounds'],
        text=f'{cid} distinct question {serial}',topic=node['title'],options=['a','b','c','d'],answer=0,
        verification_status='verified',grounding_status='book_ocr',book='source',page=1,source_quote='source',
        **extra)


@pytest.fixture
def isolated(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    monkeypatch.setattr(queue,'SessionLocal',factory)
    monkeypatch.setattr(bp,'load_catalog',lambda:{'nodes':NODES})
    monkeypatch.setattr(weekly_ranked,'prepare_config',lambda cfg:{**cfg,'weekly_scope':SCOPE,'weekly_plan':plan()})
    settings=Settings(_env_file=None,POOL_DRAFT_QUEUE_ENABLED=True,POOL_DRAFT_QUEUE_CAPACITY=16)
    monkeypatch.setattr(queue,'get_settings',lambda:settings)
    pool_core.finish_progress();pool_core.clear_cancel()
    yield factory
    pool_core.finish_progress();pool_core.clear_cancel()
    engine.dispose()


def save_bank(db, q, **flags):
    row=BankQuestion(fingerprint=question_bank._fingerprint(q,flags.get('owner_id',0)),
        major='ریاضی فیزیک',grade='دوازدهم',subject=q['subject'],content=json.dumps(q),
        owner_id=0,verified=True,status='active',uses=0,difficulty='konkur')
    for key,value in flags.items():setattr(row,key,value)
    db.add(row);db.flush()
    return row


def save_pending(db, qs, scope=SCOPE, status='pending'):
    cfg=config();cfg['weekly_scope']=scope
    row=PoolDraftJob(config=json.dumps(cfg),major='riazi',difficulty='duel',grade='دوازدهم',
        plan=json.dumps(plan()),questions=json.dumps(qs),status=status,question_count=len(qs))
    db.add(row);db.flush()
    return row


def seed_math(db):
    for cid in ['geometry','discrete','calculus-10','calculus-12']:save_bank(db,question(cid))


def test_weekly_verifier_prioritizes_missing_physics_over_more_math(isolated):
    with isolated() as db:
        seed_math(db)
        old = save_pending(db, [{**question('geometry', 20), '_queue_status':'pending'}])
        needed = save_pending(db, [{**question('physics-12', 21), '_queue_status':'pending'}])
        db.commit()
        old_id, needed_id = old.id, needed.id
    assert queue.claim_job(SCOPE) == needed_id
    with isolated() as db:
        assert db.get(PoolDraftJob, old_id).status == 'pending'
        assert db.get(PoolDraftJob, needed_id).status == 'verifying'


def test_math_stock_and_pending_physics_prioritize_missing_chemistry(isolated):
    with isolated() as db:
        seed_math(db)
        save_pending(db,[{**question(cid,i),'_queue_status':'pending'} for i,cid in enumerate(
            ['physics-10','physics-12','physics-10'])],status='verifying')
        selected=queue._weekly_draft_plan(db,config(),'riazi',plan())
    assert len(selected)==1 and selected[0]['name']=='شیمی' and selected[0]['questions']==3
    assert selected[0]['weekly_ranked_scope']==SCOPE
    assert selected[0]['maze_scope']==plan()[2]['maze_scope']


@pytest.mark.parametrize('excluded',['old-scope','corrupt','used','private','unverified','reserved','other-major','other-difficulty','ungrounded'])
def test_nonplayable_physics_stock_does_not_hide_missing_physics(isolated,excluded):
    with isolated() as db:
        seed_math(db)
        for i,cid in enumerate(['chemistry-10','chemistry-12','chemistry-10']):save_bank(db,question(cid,i))
        for i,cid in enumerate(['physics-10','physics-12','physics-10']):
            q=question(cid,i)
            flags={}
            if excluded=='old-scope':q['weekly_ranked_scope']='previous-exam'
            if excluded=='corrupt':flags['status']='corrupt'
            if excluded=='used':flags['uses']=1
            if excluded=='private':flags['owner_id']=42
            if excluded=='unverified':flags['verified']=False
            if excluded=='other-major':flags['major']='علوم تجربی'
            if excluded=='other-difficulty':flags['difficulty']='hard'
            if excluded=='ungrounded':q['grounding_status']='none'
            row=save_bank(db,q,**flags)
            if excluded=='reserved':
                db.add(GeneratedMock(student_id=0,title='reserved',major='ریاضی فیزیک',grade='دوازدهم',
                    difficulty='duel',status='pending_use',duration_minutes=15,bank_indexed=True,
                    questions=json.dumps([{**q,'bank_id':row.id}]),bank_scope='shared'))
        db.flush()
        selected=queue._weekly_draft_plan(db,config(),'riazi',plan())
    assert selected[0]['name']=='فیزیک' and selected[0]['questions']==3


@pytest.mark.parametrize('scope,status,qstatus',[
    ('previous-exam','pending','pending'),(SCOPE,'rejected','pending'),(SCOPE,'pending','rejected'),
])
def test_old_or_rejected_pending_candidates_do_not_count_as_stock(isolated,scope,status,qstatus):
    with isolated() as db:
        seed_math(db)
        for i,cid in enumerate(['chemistry-10','chemistry-12','chemistry-10']):save_bank(db,question(cid,i))
        save_pending(db,[{**question(cid,i),'_queue_status':qstatus} for i,cid in enumerate(
            ['physics-10','physics-12','physics-10'])],scope,status)
        selected=queue._weekly_draft_plan(db,config(),'riazi',plan())
    assert selected[0]['name']=='فیزیک'


def test_saved_partial_drafts_move_to_the_next_branch_without_redrafting_math(isolated):
    first=queue.create_job(config(),'riazi','duel')
    queue.append_batch(first,[question('geometry')]);queue.finish_draft(first)
    second=queue.create_job(config(),'riazi','duel')
    queue.append_batch(second,[question('discrete')]);queue.finish_draft(second)
    third=queue.create_job(config(),'riazi','duel')
    with isolated() as db:
        rows=[json.loads(db.get(PoolDraftJob,job).plan) for job in (first,second,third)]
    assert [p[0]['branch'] for p in rows]==['geometry','discrete','calculus']
    assert [p[0]['questions'] for p in rows]==[1,1,2]
    assert all(len(p)==1 and sum(r['questions'] for r in p)<10 for p in rows)


def test_append_rejects_wrong_branch_or_source_and_overwrites_untrusted_scope(isolated):
    job=queue.create_job(config(),'riazi','duel')
    right=question('geometry')
    wrong_branch={**question('geometry',1),'branch':'calculus'}
    outside=question('calculus-10',2)
    queue.append_batch(job,[wrong_branch,outside,{**right,'weekly_ranked_scope':'model-scope'}])
    with isolated() as db:qs=json.loads(db.get(PoolDraftJob,job).questions)
    assert len(qs)==1 and qs[0]['curriculum_id']=='geometry'
    assert qs[0]['weekly_ranked_scope']==SCOPE
    assert qs[0]['maze_scope']==['reviewed bounds geometry']
    assert qs[0]['_queue_status']=='pending' and qs[0]['verification_status']=='pending'


def test_duplicate_pending_question_does_not_inflate_coverage(isolated):
    with isolated() as db:
        seed_math(db)
        for i,cid in enumerate(['chemistry-10','chemistry-12','chemistry-10']):save_bank(db,question(cid,i))
        q={**question('physics-10'),'_queue_status':'pending'}
        save_pending(db,[q,q,q])
        selected=queue._weekly_draft_plan(db,config(),'riazi',plan())
    assert selected[0]['name']=='فیزیک' and selected[0]['questions']==2
    assert selected[0]['curriculum_ids']==['physics-12']
    assert selected[0]['maze_scope']['physics-12']==['reviewed bounds physics-12']


def test_repeated_chapter_stock_drafts_missing_chapter_first(isolated):
    with isolated() as db:
        seed_math(db)
        for i,cid in enumerate(['chemistry-10','chemistry-12','chemistry-10']):save_bank(db,question(cid,i))
        for i in range(6):save_bank(db,question('physics-10',i))
        selected=queue._weekly_draft_plan(db,config(),'riazi',plan())
    assert selected[0]['name']=='فیزیک'
    assert selected[0]['curriculum_ids']==['physics-12']


def test_finite_one_paper_run_keeps_drafting_after_partial_jobs(isolated,monkeypatch):
    monkeypatch.setattr(queue,'_verify_loop',lambda stop:None)
    monkeypatch.setattr(queue,'_assemble',lambda:False)
    monkeypatch.setattr(queue,'_draft_waiting',lambda state:False)
    monkeypatch.setattr(queue,'pool_generation_status',lambda:{'blocked':False,'provider':'groq'})
    calls=[];waits=[]
    def generate(_owner,draft_plan,**kwargs):
        calls.append(draft_plan)
        row=draft_plan[0]
        cid=bp.lessons_for(row,'دوازدهم')[0]['id']
        kwargs['on_drafted']([question(cid,len(calls))])
        if len(calls)==3:pool_service._update(enabled=False,status='stopped')
        return []
    def bounded_wait(seconds):
        waits.append(seconds)
        pool_service._update(enabled=False,status='stopped')
    monkeypatch.setattr(queue.mock_generation,'generate_booklet',generate)
    monkeypatch.setattr(pool_service._wake,'wait',bounded_wait)
    pool_service._save(dict(enabled=True,status='starting',config=config(1),produced=0,cursor=0))
    queue.run()
    assert len(calls)==3 and not waits
    assert pool_service.snapshot()['produced']==0
    with isolated() as db:
        assert len(db.scalars(select(PoolDraftJob)).all())==3
