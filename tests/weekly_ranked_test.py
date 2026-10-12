"""Offline regressions for rolling Maze scope and a twenty-player event."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import ArenaMatch, ArenaQueueEntry, BankQuestion, Base, GeneratedMock, User
from app.planner import mock_outline
from app.rag import exam_blueprint as bp, mock_generation as mg, pool_core, question_bank, weekly_ranked
from app.routers import arena


STUDENT = {'major': 'ریاضی فیزیک', 'grade': 'دوازدهم', 'testExams': ['ماز']}


def _schedule(tmp_path, monkeypatch):
    raw = tmp_path / 'raw'
    (raw / 'plans').mkdir(parents=True)
    pdf = raw / 'plans' / 'maze.pdf'
    pdf.write_bytes(b'original reviewed source')
    directory = tmp_path / 'cache' / 'mock_schedules'
    directory.mkdir(parents=True)
    data = dict(version=1, reviewed=True, provider='ماز', major='riazi', grade=12,
                document='maze.pdf', source_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                exams=[dict(jalali_date='1405-08-01', source_page=5,
                            sections=[dict(subject='حسابان', year=12, topics=['تابع'], quote='تابع')]),
                       dict(jalali_date='1405-09-13', source_page=5,
                            sections=[dict(subject='حسابان', year=12, topics=['مثلثات'], quote='مثلثات')])])
    path = directory / 'maze.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(mock_outline, 'get_settings', lambda: SimpleNamespace(RAW_DIR=str(raw)))
    return path, pdf, data


def test_reviewed_schedule_rolls_to_next_date_without_a_three_week_limit(tmp_path, monkeypatch):
    _schedule(tmp_path, monkeypatch)
    first = mock_outline.next_mock_outline(STUDENT, date(2026, 10, 12))
    assert first['date'] == date(2026, 10, 23)
    assert first['topics'] == {'ریاضی': ['تابع']}
    # This row is forty-one days away, beyond the old text-parser horizon.
    following = mock_outline.next_mock_outline(STUDENT, date(2026, 10, 24))
    assert following['date'] == date(2026, 12, 4)
    assert following['topics'] == {'ریاضی': ['مثلثات']}
    assert mock_outline.next_mock_outline(STUDENT, date(2026, 12, 5)) is None


def test_changed_pdf_and_unreviewed_rows_are_not_activated(tmp_path, monkeypatch):
    path, pdf, data = _schedule(tmp_path, monkeypatch)
    pdf.write_bytes(b'a replacement schedule, not yet reviewed')
    assert mock_outline.next_mock_outline(STUDENT, date(2026, 10, 12)) is None
    data['source_sha256'] = hashlib.sha256(pdf.read_bytes()).hexdigest()
    data['reviewed'] = False
    path.write_text(json.dumps(data), encoding='utf-8')
    assert mock_outline.next_mock_outline(STUDENT, date(2026, 10, 12)) is None


@pytest.mark.parametrize('student', [
    {**STUDENT, 'major': 'علوم تجربی'}, {**STUDENT, 'grade': 'یازدهم'},
    {**STUDENT, 'testExams': ['سنجش']},
])
def test_schedule_does_not_leak_between_providers_grades_or_majors(tmp_path, monkeypatch, student):
    _schedule(tmp_path, monkeypatch)
    assert mock_outline.next_mock_outline(student, date(2026, 10, 12)) is None


@pytest.fixture
def weekly(monkeypatch):
    specs = [('function-10', 'حسابان', 'تابع', 10), ('function-12', 'حسابان', 'تابع', 12),
             ('geometry', 'هندسه', 'قضیه تالس', 10), ('discrete', 'ریاضیات گسسته', 'بخش پذیری', 12),
             ('physics-10', 'فیزیک', 'ویژگی‌های فیزیکی مواد', 10),
             ('physics-12', 'فیزیک', 'حرکت بر خط راست', 12),
             ('chemistry-10', 'شیمی', 'کیهان زادگاه الفبای هستی', 10),
             ('chemistry-12', 'شیمی', 'مولکول‌ها در خدمت تندرستی', 12),
             ('irrelevant-derivative', 'حسابان', 'مشتق تابع', 12),
             ('irrelevant-function-year', 'حسابان', 'تابع', 11)]
    nodes = [dict(id=i, subject=s, title=t, year=y, majors=['riazi'],
                  sources=[dict(book='کتاب ' + s, page=20, quote=t)]) for i,s,t,y in specs]
    sections = [dict(subject=s, topics=[t], year=y, quote=t)
                for i,s,t,y in specs[:8]]
    sections[3]['topics'] = ['آشنایی با نظریه اعداد']
    sections[5]['quote'] = 'حرکت بر خط راست؛ قبل از حرکت با شتاب ثابت'
    sections[7]['quote'] = 'مولکول‌ها در خدمت تندرستی؛ تا ابتدای pH'
    outline = dict(date=date(2026, 10, 23), document='maze.pdf', source_page=5, source_digest='reviewed-sha',
                   sections=sections, topics={
                       'ریاضی':['تابع','قضیه تالس','آشنایی با نظریه اعداد'],
                       'فیزیک':['ویژگی‌های فیزیکی مواد','حرکت بر خط راست'],
                       'شیمی':['کیهان زادگاه الفبای هستی','مولکول‌ها در خدمت تندرستی']})
    monkeypatch.setattr(weekly_ranked, 'next_mock_outline', lambda *_: outline)
    monkeypatch.setattr(weekly_ranked, 'load_catalog', lambda: {'nodes':nodes})
    monkeypatch.setattr(bp, 'load_catalog', lambda: {'nodes':nodes})
    monkeypatch.setattr(arena, 'get_settings', lambda: SimpleNamespace(
        ARENA_WEEKLY_MAZE_ENABLED=True, POOL_ALLOW_LIVE_GENERATION=True))
    return nodes, outline


def test_mapping_keeps_grade_branches_and_printed_before_boundaries(weekly):
    result = weekly_ranked.preview(date(2026, 10, 12))
    assert result['available'] and result['questions'] == 10
    math, physics, chemistry = result['plan']
    assert [r['questions'] for r in result['plan']] == [4, 3, 3]
    assert set(math['curriculum_ids']) == {'function-10','function-12','geometry','discrete'}
    assert math['branches'] == {'geometry':1, 'discrete':1, 'calculus':2}
    assert physics['maze_scope']['physics-12'] == ['حرکت بر خط راست؛ قبل از حرکت با شتاب ثابت']
    assert chemistry['maze_scope']['chemistry-12'] == ['مولکول‌ها در خدمت تندرستی؛ تا ابتدای pH']
    assert {r['weekly_ranked_scope'] for r in result['plan']} == {result['scope']}


def test_number_theory_accepts_exact_book_heading_and_excludes_later_congruences():
    assert weekly_ranked.topic_matches('آشنایی با نظریه اعداد', 'نظریه اعداد')
    assert weekly_ranked.topic_matches('آشنایی با نظریه اعداد', 'بخش پذیری')
    assert not weekly_ranked.topic_matches('آشنایی با نظریه اعداد', 'هم‌نهشتی در اعداد صحیح')


def test_missing_mapping_fails_closed_instead_of_substituting_another_lesson(weekly):
    nodes, _ = weekly
    nodes[:] = [n for n in nodes if n['id'] != 'physics-12']
    result = weekly_ranked.preview()
    assert not result['available'] and result['code'] == 'maze_topics_unmapped'
    assert any(m['topic']=='حرکت بر خط راست' for m in result['missing'])
    with pytest.raises(HTTPException) as err:
        weekly_ranked.require_plan()
    assert err.value.status_code == 409


def test_changing_next_date_or_reviewed_source_changes_stock_scope(weekly):
    _, outline = weekly
    original = weekly_ranked.preview()['scope']
    outline['date'] = date(2026, 11, 6)
    following = weekly_ranked.preview()['scope']
    assert following != original
    outline['source_digest'] = 'a corrected reviewed source'
    assert weekly_ranked.preview()['scope'] not in (original, following)


def test_correcting_reviewed_page_bounds_invalidates_previously_drafted_stock(weekly):
    _, outline = weekly
    original = weekly_ranked.preview()['scope']
    # Re-reviewing a cell may correct its bounds without changing the PDF bytes.
    outline['sections'][5]['quote'] = 'حرکت بر خط راست؛ تا ابتدای سرعت متوسط'
    assert weekly_ranked.preview()['scope'] != original


def test_old_checkbox_filters_do_not_override_weekly_maze_topics(weekly):
    result = arena._pair_plan('ریاضی فیزیک','ریاضی فیزیک', ['زیست‌شناسی'], ['فیزیک'], grade='دوازدهم')
    assert result['ok'] and result['weekly']
    assert [r['name'] for r in result['plan']] == ['ریاضی','فیزیک','شیمی']
    assert arena._wanted_of(SimpleNamespace(wanted='["زیست‌شناسی"]')) == []
    assert not arena._pair_plan('ریاضی فیزیک','علوم تجربی',grade='دوازدهم')['ok']
    assert not arena._pair_plan('ریاضی فیزیک','ریاضی فیزیک',grade='یازدهم')['ok']


def test_drafting_uses_bounds_and_persists_server_scope_not_model_scope(weekly, monkeypatch):
    plan = weekly_ranked.require_plan()
    row = plan[1]
    node = next(n for n in weekly[0] if n['id']=='physics-12')
    source = dict(book='فیزیک واقعی', page=239, quote='متن OCR واقعی از حرکت بر خط راست')
    row = {**row, 'source_slots':{node['id']:dict(node=node, source=source, count=1)}}
    prompts = []
    def generate(client, prompt, *_):
        prompts.append(prompt)
        return json.dumps({'questions':[dict(source_id=node['id'], subject='فیزیک',
            topic='عنوان اختراعی', weekly_ranked_scope='model-chosen', maze_scope=['wrong'],
            text='در نمودار مکان زمان، جابه‌جایی در بازه داده‌شده چقدر است؟',
            options=['۱','۲','۳','۴'], answer=0, explanation='اختلاف مکان‌ها')]}, ensure_ascii=False)
    monkeypatch.setattr(mg,'_draft_generate',generate)
    questions = mg._draft_subject_batch(object(),row,1,['حرکت بر خط راست'],'konkur',source['quote'],
                                         8192,30,None,'دوازدهم',[])
    assert len(questions)==1
    assert 'قبل از حرکت با شتاب ثابت' in prompts[0]
    assert questions[0]['weekly_ranked_scope'] == row['weekly_ranked_scope']
    assert questions[0]['maze_scope'] == row['maze_scope'][node['id']]
    assert questions[0]['topic'] == node['title'] and questions[0]['book']==source['book']


def _questions(plan, unique='paper'):
    out=[]
    nodes = {n['id']: n for n in bp.load_catalog()['nodes']}
    for row in bp.coverage_rows(plan):
        ids=[cid for cid in row['curriculum_ids'] if not row.get('branch') or
             bp.math_branch(nodes[cid]['subject'], nodes[cid]['title']) == row['branch']]
        for i in range(row['questions']):
            cid=ids[i % len(ids)]
            out.append(dict(_id=len(out)+1, subject=row['name'], curriculum_id=cid,
                weekly_ranked_scope=row['weekly_ranked_scope'], maze_scope=row['maze_scope'][cid],
                branch=bp.math_branch(nodes[cid]['subject'], nodes[cid]['title']),
                grounding_status='book_ocr',book='کتاب واقعی',page=20,source_quote='متن واقعی کتاب',
                topic=cid,text=f'{unique} {row["name"]} سوال {i}',options=['a','b','c','d'],
                answer=0,verification_status='verified'))
    return out


@pytest.fixture
def sessions():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _paper(db, questions):
    paper=GeneratedMock(student_id=0,title='قفسه هفتگی',major='ریاضی فیزیک',grade='دوازدهم',
                        difficulty='duel',duration_minutes=15,status='pending_use',
                        questions=json.dumps(questions,ensure_ascii=False))
    db.add(paper);db.commit()
    return paper


@pytest.mark.parametrize('alter', ['unscoped','older-week','wrong-lesson','reported'])
def test_old_unscoped_wrong_or_reported_stock_is_never_served(weekly,sessions,alter):
    plan=weekly_ranked.require_plan()
    questions=_questions(plan)
    if alter=='unscoped':
        for q in questions:q.pop('weekly_ranked_scope')
    elif alter=='older-week':
        for q in questions:q['weekly_ranked_scope']='previous-week'
    elif alter=='wrong-lesson':questions[0]['curriculum_id']='irrelevant-derivative'
    with sessions() as db:
        paper=_paper(db,questions)
        if alter=='reported':
            indexed=question_bank.index_mock(db,paper)
            db.get(BankQuestion,indexed[0]['bank_id']).status='corrupt'
            db.commit()
        assert pool_core.claim_duel_booklet(db,1,2,'riazi',grade='دوازدهم',plan=plan) is None


def test_twenty_simultaneous_students_receive_ten_distinct_ready_papers_without_llm(weekly,sessions,monkeypatch):
    plan=weekly_ranked.require_plan()
    with sessions() as db:
        users=[User(username=f'event-{i}',hashed_password='unused') for i in range(20)]
        db.add_all(users);db.commit()
        user_ids=[u.id for u in users]
        for i in range(10):_paper(db,_questions(plan,f'distinct event paper {i}'))
    monkeypatch.setattr(arena,'_generate_duel_booklet',lambda *_a,**_k:pytest.fail('Ready event must not call providers'))
    def join(uid):
        # Production join/status serialize their DB reservation with this lock.
        with arena._LOCK, sessions() as db:
            entry=ArenaQueueEntry(student_id=uid,elo=1000,major='ریاضی فیزیک',grade='دوازدهم',
                                  wanted='["زیست‌شناسی"]')
            db.add(entry);db.commit()
            match=arena._try_pair(db,entry)
            return match.id if match else None
    with ThreadPoolExecutor(max_workers=20) as executor:
        results=list(executor.map(join,user_ids))
    assert len({r for r in results if r is not None})==10
    with sessions() as db:
        matches=db.execute(select(ArenaMatch)).scalars().all()
        assert len(matches)==10 and len({m.mock_id for m in matches})==10
        assert sorted([u for m in matches for u in (m.student_a_id,m.student_b_id)])==sorted(user_ids)
        assert not db.execute(select(ArenaQueueEntry)).scalars().all()
        for match in matches:
            paper=db.get(GeneratedMock,match.mock_id)
            assert paper.status=='claimed' and bp.matches_plan(json.loads(paper.questions),plan,'دوازدهم')


def test_weekly_empty_stock_never_creates_a_live_placeholder_even_when_live_is_enabled(weekly,sessions):
    pair=arena._pair_plan('ریاضی فیزیک','ریاضی فیزیک',grade='دوازدهم')
    with sessions() as db:
        entries=[ArenaQueueEntry(student_id=i,elo=1000,major='ریاضی فیزیک',grade='دوازدهم') for i in (1,2)]
        db.add_all(entries);db.commit()
        with pytest.raises(HTTPException) as err:
            arena._reserve_match(db,entries[0],entries[1],pair,'دوازدهم')
        assert err.value.status_code==409
        assert not db.execute(select(ArenaMatch)).scalars().all()
        assert not db.execute(select(GeneratedMock)).scalars().all()
