"""Coverage and provenance regressions for full math-physics mocks."""
import json
import random
import re
from collections import Counter
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.database import Base, GeneratedMock
from app.rag import exam_blueprint as bp, mock_generation as mg, question_bank as bank, pool_core
from app.rag import knowledge_base as kb
from app.routers import admin, mocks


@pytest.fixture
def catalog(monkeypatch):
    subjects = [('هندسه', 14), ('آمار و احتمال', 8), ('ریاضیات گسسته', 8),
                ('حسابان', 20), ('فیزیک', 21), ('شیمی', 22)]
    nodes = [{'id': f'{subject}-{i}', 'subject': subject, 'title': f'{subject} مبحث {i}',
              'year': 10 + i % 3, 'majors': ['riazi'],
              'sources': [{'book': f'کتاب {subject}', 'page': i + 20, 'quote': 'عنوان'}]}
             for subject, count in subjects for i in range(count)]
    monkeypatch.setattr(bp, 'load_catalog', lambda: {'nodes': nodes})
    return nodes


def test_only_math_physics_gets_the_new_full_blueprint():
    plan = mg.default_plan('riazi')
    assert [r['questions'] for r in plan] == [40, 35, 30]
    assert plan[0]['branches'] == dict(geometry=12, statistics=5, discrete=6, calculus=17)
    for major in ('tajrobi', 'insani', 'honar', 'zaban'):
        assert not any(r.get('branches') or r.get('full_mock') for r in mg.default_plan(major))
    assert admin.PoolRunIn().total_questions == 0


def test_ranked_is_ten_for_every_major_and_subset():
    for major in pool_core.POOL_MAJORS:
        plan = pool_core.generation_plan(major, ranked=True)
        assert sum(r['questions'] for r in plan) == 10
        assert not any(r.get('branches') for r in plan)
        for row in plan:
            assert sum(r['questions'] for r in pool_core.generation_plan(
                major, ranked=True, subjects=[row['name']])) == 10
    assert sum(r['questions'] for r in kb.pair_plan('ریاضی فیزیک', 'علوم تجربی')['plan']) == 10


def test_four_difficulties_validate_and_extreme_stays_in_curriculum():
    for level in ('easy', 'konkur', 'hard', 'extreme'):
        assert mocks.MockConfig(difficulty=level).difficulty == level
        assert admin.PoolRunIn(difficulty=level).difficulty == level
    prompt = mg.build_booklet_prompt([{'name': 'ریاضی', 'questions': 4}], [], 'extreme', 'OCR')
    assert 'سخت‌ترین سطح' in prompt and 'خارج از کنکور' in prompt and 'سبک صورت سوال' in prompt


def test_topics_cover_grades_without_repeating_before_exhaustion(catalog):
    nodes = bp.lessons_for({'name': 'فیزیک', 'major': 'riazi'}, 'دوازدهم')
    slots = bp.topic_slots(nodes, 35, random.Random(1))
    assert len({n['id'] for n in slots}) == 21
    assert {n['year'] for n in slots[:3]} == {10, 11, 12}
    assert all(n['year'] == 10 for n in bp.lessons_for({'name': 'فیزیک'}, 'دهم'))
    assert not bp.lessons_for({'name': 'ریاضی', 'major': 'riazi', 'majors': ['riazi', 'tajrobi']})


def test_full_generation_uses_topic_sources_and_never_model_provenance(catalog, monkeypatch):
    settings = SimpleNamespace(POOL_GENERATION_BATCH_SIZE=4, POOL_GENERATION_CONTEXT_CHARS=6000)
    monkeypatch.setattr(mg, 'get_settings', lambda: settings)
    monkeypatch.setattr(bp, 'book_excerpt', lambda node, **kw: dict(
        book=node['sources'][0]['book'], page=node['sources'][0]['page'], quote='نمونه واقعی تست کتاب'))
    prompts = []
    def generate(client, prompt, *args):
        prompts.append(prompt)
        rows = []
        for source, count in re.findall(r': (\d+) سوال؛ source_id=([^\n]+)', prompt):
            for i in range(int(source)):
                rows.append(dict(source_id=count.strip(), subject='incorrect', topic='انتگرال جعلی',
                    book='invented', page=99999, text=f'سوال مستقل {len(prompts)}-{i}-{count}',
                    options=['1', '2', '3', '4'], answer=0))
        return json.dumps({'questions': rows})
    monkeypatch.setattr(mg, '_draft_generate', generate)
    monkeypatch.setattr(mg, 'get_pool_llm_client', lambda: object())
    saved = []
    plan = mg.default_plan('riazi')
    questions = mg.generate_booklet(0, plan, on_drafted=lambda rows: saved.extend(rows), grade='دوازدهم')
    assert len(questions) == len(saved) == 105
    assert bp.matches_plan(questions, plan, 'دوازدهم')
    assert Counter(q['branch'] for q in questions if q['subject'] == 'ریاضی') == plan[0]['branches']
    assert all(q['book'] != 'invented' and q['page'] != 99999 and q['topic'] != 'انتگرال جعلی' for q in questions)
    assert all('نمونه واقعی تست کتاب' in prompt for prompt in prompts)
    assert all(q['source_quote'] == 'نمونه واقعی تست کتاب' for q in questions)
    assert 'شاهد OCR' in mg._verify_batch_prompt(questions[:2])


def test_missing_books_never_trigger_ungrounded_generation(monkeypatch):
    monkeypatch.setattr(bp, 'load_catalog', lambda: {'nodes': []})
    monkeypatch.setattr(mg, 'get_pool_llm_client', lambda: pytest.fail('No source: no provider call'))
    events = []
    assert not mg.generate_booklet(0, mg.default_plan('riazi'), report=lambda e, d: events.append(e))
    assert 'grounding_error' in events


def test_ocr_reader_uses_real_content_and_rejects_contents_only(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, 'get_settings', lambda: SimpleNamespace(OCR_DIR=str(tmp_path)))
    folder = tmp_path/'هندسه'; folder.mkdir()
    (folder/'page_0005.txt').write_text('فهرست\nدایره و وتر', encoding='utf-8')
    node = dict(title='دایره و وتر', sources=[dict(book='هندسه', page=5)])
    assert bp.book_excerpt(node) is None
    (folder/'page_0030.txt').write_text('دایره و وتر\nدر دایره‌ای با شعاع ۵، طول وتر را محاسبه کنید.', encoding='utf-8')
    excerpt = bp.book_excerpt(node)
    assert excerpt['page'] == 30 and 'شعاع ۵' in excerpt['quote']
    assert bp.book_excerpt(dict(node, sources=[dict(book='../private', page=30)])) is None


def test_contents_page_is_retrievable_when_ocr_loses_the_word_contents(tmp_path):
    from app.rag.book_curriculum import source_pages
    path = tmp_path/'page_0007.txt'
    path.write_text('کار انرژی و توان\nجریان الکتریکی و مدارهای جریان مستقیم', encoding='utf-8')
    pages, _ = source_pages({7: path})
    assert pages[7] == path.read_text(encoding='utf-8')


def test_question_excerpt_rejects_contents_even_without_contents_label(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, 'get_settings', lambda: SimpleNamespace(OCR_DIR=str(tmp_path)))
    folder=tmp_path/'فیزیک';folder.mkdir()
    titles=['کار و انرژی','الکتریسیته ساکن','مغناطیس','نوسان و امواج']
    nodes=[dict(title=t,sources=[dict(book='فیزیک',page=7)]) for t in titles]
    monkeypatch.setattr(bp,'load_catalog',lambda:{'nodes':nodes})
    (folder/'page_0007.txt').write_text('\n'.join(titles),encoding='utf-8')
    assert bp.book_excerpt(nodes[0]) is None
    (folder/'page_0030.txt').write_text('کار و انرژی: انرژی جنبشی یک جسم با جرم ۲ و سرعت ۴ چقدر است؟',encoding='utf-8')
    assert bp.book_excerpt(nodes[0])['page']==30


def test_selected_curriculum_refresh_keeps_other_books_and_caches_validated_results(tmp_path, monkeypatch):
    from scripts import refresh_exam_curriculum as refresh
    folder = tmp_path/'ocr'/'فیزیک ریاضی.pdf'; folder.mkdir(parents=True)
    (folder/'page_0007.txt').write_text('میدان الکتریکی', encoding='utf-8')
    path = tmp_path/'catalog.json'
    other = dict(id='other', title='تابع', subject='ریاضی', year=10, majors=['riazi'],
                 sources=[dict(book='ریاضی', page=7)])
    path.write_text(json.dumps(dict(version=1,nodes=[other],edges=[],books=['ریاضی'])), encoding='utf-8')
    monkeypatch.setattr(refresh, 'get_settings', lambda: SimpleNamespace(OCR_DIR=str(tmp_path/'ocr')))
    monkeypatch.setattr(refresh.curriculum, 'catalog_path', lambda: path)
    calls = []
    node = dict(id='physics', title='میدان الکتریکی', subject='فیزیک', year=0,
        majors=['riazi'], sources=[dict(book='فیزیک ریاضی',page=7,quote='میدان الکتریکی')])
    monkeypatch.setattr(refresh.curriculum, 'extract_book', lambda *args: calls.append(1) or [node])
    result = refresh.refresh(['فیزیک ریاضی'], object())
    assert {n['id'] for n in result['nodes']} == {'other','physics'}
    refresh.refresh(['فیزیک ریاضی'], object())
    assert calls == [1]


def test_bank_rejects_wrong_branch_and_topic_concentration(catalog):
    engine = create_engine('sqlite://'); Base.metadata.create_all(engine)
    plan = mg.default_plan('riazi')
    with sessionmaker(bind=engine)() as db:
        rows = []
        for section in bp.coverage_rows(plan):
            nodes = bp.lessons_for(section)
            for i in range(section['questions']):
                node = nodes[i % len(nodes)]
                rows.append(dict(subject=section['name'], branch=section.get('branch', ''),
                    curriculum_id=node['id'], topic=node['title'], text=f'{node["id"]} {i}',
                    book='book', page=20, source_quote='OCR', grounding_status='book_ocr',
                    options=['a', 'b', 'c', 'd'], answer=0, verification_status='verified'))
        mock = GeneratedMock(student_id=0, title='source', major='ریاضی فیزیک', grade='دوازدهم',
            difficulty='konkur', bank_scope='shared', status='bank_only', questions=json.dumps(rows))
        db.add(mock); db.flush(); bank.index_mock(db, mock); db.commit()
        selected = bank.assemble(db, 0, plan, ['ریاضی فیزیک'], prefer_used=False)
        assert len(selected) == 105 and bp.matches_plan(selected, plan)
        # Enough total questions cannot compensate for the missing geometry.
        for q in db.query(bank.BankQuestion).filter_by(subject='ریاضی'):
            data = json.loads(q.content)
            if data['branch'] == 'geometry':
                data['branch'] = 'calculus'; q.content = json.dumps(data)
        db.commit()
        assert not bank.assemble(db, 0, plan, ['ریاضی فیزیک'])
