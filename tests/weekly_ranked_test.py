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


@pytest.mark.parametrize('major', ['', None])
def test_legacy_empty_major_uses_the_same_math_default_as_planner(tmp_path, monkeypatch, major):
    _schedule(tmp_path, monkeypatch)
    result = mock_outline.next_mock_outline({'major':major,'grade':None,'testExams':[]}, date(2026,10,18))
    assert result['date'] == date(2026,10,23)
    assert result['provider'] == 'ماز'
    assert result['topics'] == {'ریاضی':['تابع']}


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
                topic=cid,text=f'{unique} {row["name"]} {cid} سوال {i}',options=['a','b','c','d'],
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


def _previous_scope(weekly, monkeypatch):
    import copy
    current=weekly_ranked.preview()
    previous=copy.deepcopy(current)
    previous.update(date='2026-10-09',scope='reviewed-previous-week')
    for row in previous['plan']:row['weekly_ranked_scope']=previous['scope']
    monkeypatch.setattr(weekly_ranked,'preview',lambda day=None:
                        previous if day==date(2026,10,9) else current)
    monkeypatch.setattr(mock_outline,'_structured_outlines',lambda *args:[{'date':date(2026,10,9)}])
    return current,previous


def test_arena_falls_back_to_verified_previous_scope_without_claiming_stock(weekly,sessions,monkeypatch):
    current,previous=_previous_scope(weekly,monkeypatch)
    with sessions() as db:
        paper=_paper(db,_questions(previous['plan']))
        result=weekly_ranked.available_preview(db,1,'دوازدهم')
        assert result['fallback'] and result['stock_available']
        assert result['date']=='2026-10-09' and result['requested_date']==current['date']
        assert result['scope']==previous['scope'] and paper.status=='pending_use'
        assert all(q.uses==0 for q in db.execute(select(BankQuestion)).scalars())


def test_current_scope_keeps_priority_over_previous_stock(weekly,sessions,monkeypatch):
    current,previous=_previous_scope(weekly,monkeypatch)
    with sessions() as db:
        _paper(db,_questions(previous['plan'],'old'))
        _paper(db,_questions(current['plan'],'current'))
        result=weekly_ranked.available_preview(db,1,'دوازدهم')
        assert result['stock_available'] and not result['fallback'] and result['scope']==current['scope']


def test_previous_valid_scope_is_available_while_next_curriculum_is_unmapped(weekly,sessions,monkeypatch):
    current,previous=_previous_scope(weekly,monkeypatch)
    current.update(available=False,code='maze_topics_unmapped')
    with sessions() as db:
        _paper(db,_questions(previous['plan']))
        result=weekly_ranked.available_preview(db,1,'دوازدهم')
        assert result['available'] and result['fallback'] and result['scope']==previous['scope']


def test_mock_archive_lists_and_opens_previous_maze_without_reassigning_the_source(weekly,sessions,monkeypatch):
    from app.rag import previous_maze
    from app.routers import mocks
    current, previous = _previous_scope(weekly, monkeypatch)
    monkeypatch.setattr(weekly_ranked, 'today', lambda: date(2026, 10, 31))
    monkeypatch.setattr(mg, 'generate_booklet', lambda *_a, **_k: pytest.fail('Archive must not call an LLM'))
    with sessions() as db:
        db.add(User(id=1, username='archive-reader', hashed_password='unused'))
        source = _paper(db, _questions(previous['plan']))
        items = previous_maze.available(db, 1, STUDENT)
        assert len(items) == 1 and items[0]['exam_date'] == '2026-10-09'
        assert items[0]['total_questions'] == 10
        original_questions = source.questions
        response = previous_maze.create(db, 1, STUDENT, date(2026, 10, 9))
        assert response['mock_id'] != source.id and response['source'] == 'previous_maze'
        assert response['total_questions'] == 10 and response['fallback']
        assert source.student_id == 0 and source.status == 'pending_use'
        assert source.questions == original_questions
        copy = db.get(GeneratedMock, response['mock_id'])
        assert {q['weekly_ranked_scope'] for q in json.loads(copy.questions)} == {previous['scope']}
        public = mocks.get_mock(copy.id, db.get(User, 1), db)
        assert len(public['questions']) == 10
        assert all('answer' not in q and 'explanation' not in q for q in public['questions'])


def test_mock_archive_http_selection_refunds_a_failed_open(weekly,sessions,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.auth.deps import get_current_user, get_db
    from app.routers import mocks
    _, previous = _previous_scope(weekly, monkeypatch)
    monkeypatch.setattr(weekly_ranked, 'today', lambda: date(2026, 10, 31))
    charges, refunds = [], []
    monkeypatch.setattr(mocks, 'consume_ai_use', lambda *args: charges.append(args))
    monkeypatch.setattr(mocks, 'release_ai_use', lambda *args: refunds.append(args))
    with sessions() as db:
        user = User(id=1, username='archive-http', hashed_password='unused')
        db.add(user); _paper(db, _questions(previous['plan']))
        app = FastAPI(); app.include_router(mocks.router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        with TestClient(app) as client:
            listing = client.get('/api/mocks/previous-maze').json()['items']
            assert listing
            assert listing[0]['exam_date'] == '2026-10-09'
            response = client.post('/api/mocks/previous-maze', json={'exam_date':'2026-10-09'})
            assert response.status_code == 200 and response.json()['total_questions'] == 10
            assert len(client.get(f"/api/mocks/{response.json()['mock_id']}").json()['questions']) == 10
            failed = client.post('/api/mocks/previous-maze', json={'exam_date':'2026-11-06'})
            assert failed.status_code == 409 and len(charges) == 2 and len(refunds) == 1


@pytest.mark.parametrize('invalid', ['corrupt', 'private', 'mixed-scope', 'wrong-grade', 'wrong-major', 'future'])
def test_mock_archive_rechecks_stock_and_access_when_opening(weekly,sessions,monkeypatch,invalid):
    from app.rag import previous_maze
    _, previous = _previous_scope(weekly, monkeypatch)
    monkeypatch.setattr(weekly_ranked, 'today', lambda: date(2026, 10, 31))
    student = dict(STUDENT)
    with sessions() as db:
        questions = _questions(previous['plan'])
        if invalid == 'mixed-scope': questions[0]['weekly_ranked_scope'] = 'other'
        source = _paper(db, questions)
        if invalid == 'private':
            source.student_id = 999; source.bank_scope = 'private'; source.status = 'claimed'
        if invalid == 'corrupt':
            indexed = question_bank.index_mock(db, source)
            db.get(BankQuestion, indexed[0]['bank_id']).status = 'corrupt'
        if invalid == 'wrong-grade': student['grade'] = 'یازدهم'
        if invalid == 'wrong-major': student['major'] = 'علوم تجربی'
        db.commit()
        with pytest.raises(HTTPException) as error:
            previous_maze.create(db, 1, student,
                date(2026, 11, 6) if invalid == 'future' else date(2026, 10, 9))
        assert error.value.status_code == 409
        assert db.query(GeneratedMock).count() == 1


@pytest.mark.parametrize('invalid',['corrupt','private','partial-mixed-weeks'])
def test_fallback_never_uses_corrupt_private_or_mixed_week_stock(weekly,sessions,monkeypatch,invalid):
    current,previous=_previous_scope(weekly,monkeypatch)
    with sessions() as db:
        questions=_questions(previous['plan'])
        if invalid=='partial-mixed-weeks':
            questions=[q for q in questions if q['subject']!='ریاضی']
            _paper(db,[q for q in _questions(current['plan'],'current') if q['subject']=='ریاضی'])
        paper=_paper(db,questions)
        if invalid=='private':
            paper.student_id=99;paper.status='claimed';paper.bank_scope='private';db.commit()
        elif invalid=='corrupt':
            indexed=question_bank.index_mock(db,paper)
            db.get(BankQuestion,indexed[-1]['bank_id']).status='corrupt';db.commit()
        result=weekly_ranked.available_preview(db,1,'دوازدهم')
        assert not result['stock_available'] and not result['fallback']


def test_pairing_serves_both_players_one_previous_scope_without_live_generation(weekly,sessions,monkeypatch):
    current,previous=_previous_scope(weekly,monkeypatch)
    monkeypatch.setattr(arena,'_generate_duel_booklet',lambda *a,**k:pytest.fail('No provider call for archive fallback'))
    with sessions() as db:
        _paper(db,_questions(previous['plan']))
        entries=[ArenaQueueEntry(student_id=i,elo=1000,major='ریاضی فیزیک',grade='دوازدهم') for i in (1,2)]
        db.add_all(entries);db.commit()
        with arena._LOCK:match=arena._try_pair(db,entries[1])
        assert match and match.mock_ready
        assert {match.student_a_id,match.student_b_id}=={1,2}
        paper=db.get(GeneratedMock,match.mock_id)
        questions=json.loads(paper.questions)
        assert len(questions)==10 and {q['weekly_ranked_scope'] for q in questions}=={previous['scope']}


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
