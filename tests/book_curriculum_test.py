import json
from types import SimpleNamespace

from app.rag import book_curriculum as books
from app.rag import knowledge_graph as graph


def lesson(title='تابع',page=7,year=11,**extra):
    return {'title':title,'page':page,'quote':title,'year':year,
            'grade_page':2,'grade_quote':'حسابان ۱ پایه یازدهم',**extra}


def test_rejects_invented_lessons_and_page_citations():
    pages={2:'حسابان ۱ پایه یازدهم',7:'درس ۱: تابع\nدرس ۲: حد و پیوستگی'}
    nodes=books.validate_lessons({'lessons':[lesson(),lesson('انتگرال'),lesson(page=99),
        lesson(quote='عنوان ساخته شده'),lesson('حد و پیوستگی')]},pages,'حسابان 1 خیلی سبز')
    assert [n['title'] for n in nodes]==['تابع','حد و پیوستگی']
    assert all(n['year']==11 and n['sources'][0]['page']==7 for n in nodes)


def test_grade_needs_source_evidence_and_mixed_book_stays_unknown():
    pages={2:'حسابان ۱ پایه یازدهم؛ دهم و دوازدهم هم موجود است',7:'تابع'}
    rows=[lesson(year=12),lesson(grade_quote=pages[2]),lesson(grade_quote='پایه یازدهم')]
    nodes=books.validate_lessons({'lessons':rows},pages,'حسابان جامع')
    assert all(n['year']==0 for n in nodes)
    assert books.validate_lessons({'lessons':'bad'},pages,'حسابان 1')==[]


def test_minor_ocr_repairs_are_allowed_but_unrelated_titles_are_not():
    assert books.title_matches('مشتق‌گیری','مشتق گیری')
    assert books.title_matches('تابع','درس ۱: تابع')
    assert not books.title_matches('انتگرال معین','درس ۳: تابع و ویژگی آن')
    assert books.norm('يک ١٢')==books.norm('یک ۱۲')
    assert books.source_quote('تبدیل نمودارهای تابع','درس ۱: تبدیل نمودارهاى تابع')=='تبدیل نمودارهاى تابع'
    assert books.source_quote('ترمودینامیک و انرژی گیبی','درس ۱: تبدیل نمودارهای تابع') is None


def test_repaired_quote_is_replaced_with_literal_page_text():
    pages={7:'درس ۱: قواعد مشتق‌گبری'}
    rows=[lesson('قواعد مشتق‌گیری',quote='قواعد مشتق‌گیری')]
    nodes=books.validate_lessons({'lessons':rows},pages,'حسابان 2')
    assert nodes[0]['sources'][0]['quote']=='قواعد مشتق‌گبری'


def test_bare_lesson_numbers_and_empty_ocr_labels_are_not_curriculum(tmp_path):
    pages={7:'درس ۱\nدرس ۲: تابع\nدرسنامه'}
    nodes=books.validate_lessons({'lessons':[lesson('درس ۱'),lesson('درسنامه'),
        lesson('درس ۲: تابع')]},pages,'حسابان 1')
    assert [n['title'] for n in nodes]==['تابع']
    root=tmp_path/'ocr'; directory=root/'حسابان 1'; (directory/'pages').mkdir(parents=True)
    (directory/'page_0007.txt').write_text('درس ۲: تابع',encoding='utf-8')
    (directory/'pages/page_0007.json').write_text(json.dumps({'data':{
        'lesson_title':'انتگرال','page_text':'','questions':[{'text':'made up'}]}}),encoding='utf-8')
    assert books.discover_books(root)['حسابان 1'][7].suffix=='.txt'


def test_grade_words_do_not_confuse_yazdahom_with_dahom():
    pages={2:'حسابان ۱ پایه یازدهم',7:'تابع'}
    nodes=books.validate_lessons({'lessons':[lesson(year=10),lesson(year=11)]},pages,'حسابان 1')
    assert [n['year'] for n in nodes]==[0,11]
    pages[2]='تبلیغ آزمون برای پایه دهم، یازدهم و دوازدهم'
    node=books.validate_lessons({'lessons':[lesson(year=10,grade_quote='پایه دهم')]},pages,'حسابان 1')[0]
    assert node['year']==0


def test_prerequisites_cannot_cycle_cross_majors_or_require_later_grades():
    nodes=[{'id':'a','year':10,'majors':['riazi']},{'id':'b','year':11,'majors':['riazi']},
           {'id':'c','year':0,'majors':['tajrobi']},{'id':'d','year':11,'majors':['riazi']}]
    edges=books.valid_edges([{'source':a,'target':b} for a,b in [('a','b'),('b','a'),('a','c'),
        ('a','x'),('a','a'),('b','d'),('d','b')]],nodes)
    assert [(e['source'],e['target']) for e in edges]==[('a','b'),('b','d')]
    assert all(e['basis']=='model_inferred' for e in edges)


def test_missing_books_never_fall_back_to_model_memory(monkeypatch):
    monkeypatch.setattr(graph,'load_catalog',lambda:{})
    result=graph.build_graph('علوم انسانی')
    assert result['nodes']==result['edges']==[]
    assert result['curriculum']['status']=='missing_books'


def test_major_filter_unknown_grade_and_no_artificial_sequence_lock(monkeypatch):
    nodes=[{'id':i,'subject':s,'title':t,'year':y,'importance':3,'majors':[m],
            'sources':[{'book':s,'page':7,'quote':t}]} for i,s,t,y,m in
           [('a','حسابان','تابع',11,'riazi'),('b','حسابان','مشتق',0,'riazi'),
            ('c','زیست‌شناسی','گوارش',10,'tajrobi')]]
    monkeypatch.setattr(graph,'load_catalog',lambda:{'nodes':nodes,'edges':[],'complete':True})
    result=graph.build_graph('ریاضی فیزیک',{('حسابان','تابع'):{'attempted':4,'correct':3,'wrong':1}})
    assert not any(n['id']=='c' for n in result['nodes'])
    subject=next(n for n in result['nodes'] if n['kind']=='subject')
    assert subject['accuracy']==.75
    assert next(n for n in result['nodes'] if n['id']=='b')['available']
    assert next(n for n in result['nodes'] if n['id']=='b')['year']==0


def test_cache_resumes_without_new_model_calls(tmp_path,monkeypatch):
    monkeypatch.setattr(books,'catalog_path',lambda:tmp_path/'catalog.json')
    root=tmp_path/'ocr'; directory=root/'حسابان 1'; directory.mkdir(parents=True)
    (directory/'page_2.txt').write_text('حسابان ۱ پایه یازدهم',encoding='utf-8')
    (directory/'page_7.txt').write_text('درس ۱: تابع',encoding='utf-8')
    client=SimpleNamespace(last_error='',generate=lambda *a,**kw:json.dumps({'lessons':[lesson()]}))
    events=[]
    first=books.rebuild(client,root=root,infer=False,on_progress=events.append)
    assert first['complete'] and len(first['nodes'])==1 and events[0]['status']=='extracted'
    client.generate=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('cached rebuild called the LLM'))
    second=books.rebuild(client,root=root,infer=False,on_progress=events.append)
    assert second['nodes']==first['nodes'] and events[-1]['status']=='cached'


def test_provider_failure_preserves_catalog_and_does_not_infer_or_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(books,'catalog_path',lambda:tmp_path/'catalog.json')
    old={'version':1,'nodes':[{'id':'saved','title':'تابع','majors':['riazi']}],
         'edges':[],'books':['حسابان 1']}
    books.save_json(books.catalog_path(),old)
    root=tmp_path/'ocr'
    for name in ['حسابان 1','شیمی 1']:
        directory=root/name; directory.mkdir(parents=True)
        (directory/'page_2.txt').write_text('فهرست\nدرس ۱: تابع',encoding='utf-8')
    calls=[]
    client=SimpleNamespace(last_error='daily quota exhausted',generate=lambda *a,**kw:calls.append(1) or '')
    result=books.rebuild(client,root=root,infer=True)
    assert len(calls)==1 and result['nodes']==old['nodes'] and not result['complete']


def test_missing_source_directory_preserves_previously_uploaded_catalog(tmp_path,monkeypatch):
    monkeypatch.setattr(books,'catalog_path',lambda:tmp_path/'catalog.json')
    old={'version':1,'nodes':[{'id':'saved'}],'edges':[],'books':['حسابان 1']}
    books.save_json(books.catalog_path(),old)
    client=SimpleNamespace(generate=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('unexpected LLM')))
    result=books.rebuild(client,root=tmp_path/'missing')
    assert result['nodes']==old['nodes'] and result['books']==old['books'] and not result['complete']


def test_book_titles_and_incomplete_headings_are_not_lessons():
    pages={7:'پرسش‌های چهارگزینه‌ای شیمی ۳\nآشنایی با مفهوم\nتوان‌های\nفصل اول: مولکول‌ها در خدمت تندرستی'}
    nodes=books.validate_lessons({'lessons':[lesson(t) for t in [
        'پرسش‌های چهارگزینه‌ای شیمی ۳','آشنایی با مفهوم','توان‌های','فصل اول: مولکول‌ها در خدمت تندرستی']]},pages,'شیمی 3')
    assert [n['title'] for n in nodes]==['مولکول‌ها در خدمت تندرستی']


def test_math_book_track_is_taken_from_its_own_front_matter():
    pages={2:'پرسش‌های چهارگزینه‌ای ریاضیات تجربی جامع',7:'درس ۱: تابع'}
    node=books.validate_lessons({'lessons':[lesson()]},pages,'ریاضی جامع خیلی سبز جلد اول')[0]
    assert node['majors']==['tajrobi']
    assert node['sources'][0]['major_page']==2
    assert 'تجربی' in node['sources'][0]['major_quote']
