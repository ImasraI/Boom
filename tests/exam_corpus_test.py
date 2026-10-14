import copy
import json
from pathlib import Path

import httpx
import pytest

from app.rag import exam_corpus as corpus, exam_scanning as scanning, exam_style as style
from app.rag import exam_inventory
from app.rag.exam_vision import Credential, VisionFleet, parse_transcript, retry_seconds


def page():
    return {'page_kind':'questions','source_major':'riazi','major_evidence':'گروه علوم ریاضی و فنی',
        'complete':True,'uncertainties':[],'questions':[{'number':7,'subject':'ریاضی','topic':'تابع درجه دوم',
        'text':r'برای تابع $f(x)=x^2-3x$ کدام بازه مجاز است؟','options':['۱','۲','۳','۴'],
        'bbox':[.1,.2,.9,.4],'has_figure':False,'figure_description':'','answer_index':None,'answer_evidence':'',
        'uncertainties':[],'design':{'skills':['بررسی تابع'],'representation':'equation','solution_strategy':'بررسی بازه',
        'distractor_mechanisms':['اشتباه علامت'],'difficulty_mechanism':'ترکیب شرط‌ها','wording_features':[]}}]}


@pytest.mark.parametrize('path',['../x','a/../../x','/x',r'\x','C:/x','a:x'])
def test_source_paths_cannot_escape(tmp_path,path):
    with pytest.raises(ValueError):corpus.safe_path(tmp_path,path)


def test_atomic_and_worker_lock(tmp_path):
    corpus.atomic_json(tmp_path/'data.json',{'متن':2})
    assert corpus.read_json(tmp_path/'data.json')=={'متن':2}
    with corpus.job_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with corpus.job_lock(tmp_path):pass
    with corpus.job_lock(tmp_path):pass
    assert not corpus.worker_alive(-1)


def test_native_resume_checks_identity_and_render_dpi(tmp_path):
    import pymupdf
    source=tmp_path/'mocks/same.pdf';source.parent.mkdir()
    doc=pymupdf.open();p=doc.new_page();p.insert_text((40,40),'Original formula x^2-3x');doc.save(source);doc.close()
    sha=corpus.digest(source);root=tmp_path/'data'
    corpus.atomic_json(root/'inventory.json',{'documents':[{'document_id':sha,'name':source.name,'path':'mocks/same.pdf','pages':1}]})
    result=corpus.extract_native(tmp_path,root)
    assert result['completed']==1 and result['failed']==0
    path=corpus.native_path(root,sha,1);saved=corpus.read_json(path)
    assert 'x^2-3x' in saved['literal_text'] and saved['blocks']
    saved['pdf_page']=2;corpus.atomic_json(path,saved)
    corpus.extract_native(tmp_path,root)
    assert corpus.read_json(path)['pdf_page']==1
    image=root/'page.png';corpus.render_page(source,1,image,72);size=image.stat().st_size
    corpus.render_page(source,1,image,144)
    assert image.stat().st_size!=size and corpus.read_json(image.with_suffix('.render.json'))['dpi']==144
    with source.open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='Source content changed'):corpus.extract_native(tmp_path,root)


@pytest.mark.parametrize('field,value,issue',[
 ('number',[], 'invalid_question_number'),('number',True,'invalid_question_number'),
 ('options',['۱','۲'],'incomplete_options'),('bbox',[0,0,float('nan'),1],'invalid_bbox'),
 ('answer_index',2,'unproven_answer'),('text','a\frac{x}{2} corrupt text','corrupted_math_escape'),
 ('has_figure',None,'figure_flag_missing'),('design',{},'invalid_design')])
def test_uncertain_or_malformed_questions_never_qualify(field,value,issue):
    data=page();data['questions'][0][field]=value
    assert issue in scanning.validate_page(data)


@pytest.mark.parametrize('replacement',[r'x^2+3x',r'x^3-3x',r'x^2-2x'])
def test_visual_agreement_does_not_hide_scientific_symbol_changes(replacement):
    a=page();b=copy.deepcopy(a);b['questions'][0]['text']=b['questions'][0]['text'].replace('x^2-3x',replacement)
    assert not scanning.agrees(a,b)
    b=copy.deepcopy(a);b['questions'][0]['options'].reverse()
    assert not scanning.agrees(a,b)
    assert scanning.agrees(a,a)


def test_json_serialization_repair_never_invents_missing_content():
    assert parse_transcript(r'{"text":"\sqrt{x}"}')=={'text':r'\sqrt{x}'}
    assert parse_transcript('{"text":"unfinished') is None
    assert parse_transcript('```json\n{"x":1}\n```')=={'x':1}
    assert parse_transcript(r'{"math":"\frac{x}{2}"}') is None
    assert parse_transcript(r'{"math":"\nabla f"}') is None
    assert parse_transcript(r'{"math":"\\frac{x}{2}"}')=={'math':r'\frac{x}{2}'}


def fleet(tmp_path,handler,model='gemini-3.6-flash',key='private-test-key'):
    spec=Credential('gemini',key,model,'https://example.test/v1beta/openai')
    transport=httpx.MockTransport(handler)
    return VisionFleet([spec],tmp_path,minimum_interval=0,
        client_factory=lambda _:httpx.Client(transport=transport)),spec


def test_native_vision_uses_real_image_and_header_secret_and_ignores_thoughts(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'fake png bytes')
    seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[
            {'thought':True,'text':'private reasoning'}, {'text':json.dumps(page())}]}}],'usageMetadata':{'promptTokenCount':2}})
    f,s=fleet(tmp_path,handler);r=f.request('exact OCR',image,'gemini')
    assert r['ok'] and r['data']==page() and 'private reasoning' not in json.dumps(r)
    request=seen[0];payload=json.loads(request.content)
    assert s.key not in str(request.url) and s.key not in request.content.decode() and s.key not in json.dumps(r)
    assert request.headers['x-goog-api-key']==s.key
    assert payload['contents'][0]['parts'][1]['inlineData']['data']
    assert payload['generationConfig']['thinkingConfig']['thinkingLevel']=='HIGH'
    assert payload['generationConfig']['mediaResolution']=='MEDIA_RESOLUTION_HIGH'


def test_daily_quota_is_persisted_and_not_probed_again(tmp_path):
    calls=[];image=tmp_path/'i.png';image.write_bytes(b'png')
    def handler(request):
        calls.append(request)
        return httpx.Response(429,headers={'retry-after':'1'},json={'error':{'message':'Daily request quota exceeded'}})
    f,s=fleet(tmp_path,handler);r=f.request('p',image)
    assert r['error']=='provider_daily_quota' and r['retry_at']>__import__('time').time()+60
    assert f.request('p',image)['error']=='no_ready_credentials' and len(calls)==1
    reloaded,_=fleet(tmp_path,handler)
    assert reloaded.request('p',image)['error']=='no_ready_credentials' and len(calls)==1


def test_corrupt_quota_state_fails_closed_before_any_provider_call(tmp_path):
    corpus.atomic_json(tmp_path/'vision-quota.json',[])
    with pytest.raises(RuntimeError,match='Invalid saved quota'):fleet(tmp_path,lambda request:pytest.fail('Provider must not be called'))
    (tmp_path/'vision-quota.json').write_text('{unfinished')
    with pytest.raises(RuntimeError,match='Invalid saved quota'):fleet(tmp_path,lambda request:pytest.fail('Provider must not be called'))


def test_credential_rejection_applies_across_models_without_leaking_secret(tmp_path):
    image=tmp_path/'i.png';image.write_bytes(b'png')
    def handler(request):return httpx.Response(401,json={'error':{'message':'Rejected private-test-key https://secret.test/key'}})
    f,_=fleet(tmp_path,handler);r=f.request('p',image)
    assert 'private-test-key' not in json.dumps(r) and 'secret.test' not in json.dumps(r)
    other,_=fleet(tmp_path,handler,model='another-model')
    assert other.request('p',image)['error']=='no_ready_credentials'


def test_truncated_provider_response_is_not_a_valid_transcript(tmp_path):
    image=tmp_path/'i.png';image.write_bytes(b'png')
    f,_=fleet(tmp_path,lambda r:httpx.Response(200,json={'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':json.dumps(page())}]}}]}))
    assert f.request('p',image)['error']=='incomplete_transcription'


def test_retry_delay_preserves_longest_provider_hint():
    response=httpx.Response(429,headers={'retry-after':'5'},json={'error':{'message':'Try again in 1h2m3s'}})
    assert retry_seconds(response,True,'groq')==3723


def save_review(root,*,stale=False):
    sha='a'*64;folder=root/'documents'/sha/'vision';image=root/'documents'/sha/'images/page_00001.png'
    image.parent.mkdir(parents=True);image.write_bytes(b'png')
    data=page();row={'ok':True,'data':data,'document_id':sha,'document_name':'sample.pdf','pdf_page':1,
        'image':str(image.relative_to(root)),'coverage':'selected_questions'}
    corpus.atomic_json(folder/'page_00001.visual.json',row)
    corpus.atomic_json(folder/'page_00001.review.json',{'approved':True,'reviewer':'visual test reviewer','review_kind':'visual',
        'data_sha256':'wrong' if stale else corpus.payload_digest(data),'image_sha256':corpus.digest(image),'reviewed_questions':[7]})
    return data,folder


def test_review_is_bound_to_exact_transcript_and_original_image(tmp_path):
    data,folder=save_review(tmp_path,stale=True)
    assert scanning.standardize(tmp_path)['qualified_references']==0
    review=corpus.read_json(folder/'page_00001.review.json');review['data_sha256']=corpus.payload_digest(data)
    corpus.atomic_json(folder/'page_00001.review.json',review)
    assert scanning.standardize(tmp_path)['qualified_references']==1
    record=corpus.read_json(tmp_path/'style-index.json')['records'][0]
    assert record['extraction_state']=='visual_checked' and not record['human_reviewed']
    assert not record['page_fully_transcribed'] and record['scientific_state']=='not_checked'
    row=corpus.read_json(folder/'page_00001.visual.json');row['data']['questions'][0]['text']+=' modified'
    corpus.atomic_json(folder/'page_00001.visual.json',row)
    assert scanning.standardize(tmp_path)['qualified_references']==0


def test_style_retrieval_requires_current_subject_major_topic_and_qualified_record(tmp_path):
    save_review(tmp_path);scanning.standardize(tmp_path);index=tmp_path/'style-index.json'
    plan=[{'name':'ریاضی','major':'riazi'}];topics=['تابع درجه دوم: ۱ سوال']
    assert len(style.references(plan,topics,path=index))==1
    assert not style.references([{'name':'ریاضی','major':'tajrobi'}],topics,path=index)
    assert not style.references([{'name':'ریاضی'}],topics,path=index)
    assert not style.references(plan,['انتگرال'],path=index)
    assert not style.references(plan,[],path=index)
    context=style.context(plan,topics,path=index)
    assert 'exam_style_data' in context and 'answer_index' not in context
    assert style.is_source_copy(page()['questions'][0]['text'],plan,topics,path=index)
    row=corpus.read_json(index);row['records'][0]['literal']['text']='changed without review'
    corpus.atomic_json(index,row)
    assert not style.references(plan,topics,path=index)


def test_layout_schema_and_resume_question_groups(tmp_path):
    layout={'page_kind':'questions','source_major':'riazi','major_evidence':page()['major_evidence'],
        'complete':True,'uncertainties':[],'question_numbers':[7]}
    class Stub:
        calls=0
        def request(self,prompt,image,provider):
            self.calls+=1
            return {'ok':True,'data':layout if prompt==scanning.LAYOUT_PROMPT else page(),'model':'stub'}
    f=Stub();image=tmp_path/'image.png';image.write_bytes(b'png')
    r=scanning.structured_scan(tmp_path,tmp_path/'scan',image,f,'groq')
    assert r['ok'] and len(r['data']['questions'])==1 and f.calls==2
    assert scanning.structured_scan(tmp_path,tmp_path/'scan',image,f,'groq')['ok'] and f.calls==2
    layout['question_numbers']=[True]
    assert not scanning.validate_layout(layout)


def test_hard_request_capacity_error_cannot_create_retry_loop(tmp_path):
    image=tmp_path/'i.png';image.write_bytes(b'png');calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(429,json={'error':{'message':'Request too large. Expected output tokens exceed limit 1000'}})
    f,_=fleet(tmp_path,handler)
    assert f.request('p',image)['error']=='provider_request_too_large'
    assert f.next_ready('gemini') is None
    assert f.request('p',image)['error']=='no_ready_credentials' and len(calls)==1


def test_prompt_style_stays_separate_from_grounding(monkeypatch,tmp_path):
    from app.rag import mock_generation as mg
    save_review(tmp_path);scanning.standardize(tmp_path)
    monkeypatch.setattr(style,'INDEX',tmp_path/'style-index.json')
    plan=[{'name':'ریاضی','major':'riazi','questions':1}]
    grounded=mg.build_booklet_prompt(plan,['تابع درجه دوم'],'hard','[source_id: valid-book] current allowed concept')
    assert '<exam_style_data>' in grounded and 'current allowed concept' in grounded
    assert 'answer_index' not in grounded.split('<exam_style_data>')[1]
    ungrounded=mg.build_booklet_prompt(plan,['تابع درجه دوم'],'hard','')
    assert '<exam_style_data>' not in ungrounded


def test_no_qualified_styles_from_blanket_or_stale_review(tmp_path):
    _,folder=save_review(tmp_path)
    review=corpus.read_json(folder/'page_00001.review.json');review.pop('reviewed_questions')
    corpus.atomic_json(folder/'page_00001.review.json',review)
    assert scanning.standardize(tmp_path)['qualified_references']==0


def test_source_copy_is_discarded_before_normal_verification(monkeypatch,tmp_path):
    from app.rag import mock_generation as mg
    save_review(tmp_path);scanning.standardize(tmp_path);monkeypatch.setattr(style,'INDEX',tmp_path/'style-index.json')
    q=page()['questions'][0]
    raw=json.dumps({'questions':[{'subject':'ریاضی','topic':'تابع درجه دوم','text':q['text'],
        'options':q['options'],'answer':0,'explanation':'محتوای کپی شده برای آزمون'}]})
    monkeypatch.setattr(mg,'_draft_generate',lambda *args:raw)
    result=mg._draft_subject_batch(object(),{'name':'ریاضی','major':'riazi'},1,['تابع درجه دوم'],
                                   'konkur','book quote',8192,60,None,'دوازدهم',[])
    assert result==[]


def test_only_changing_parameters_does_not_make_a_new_source_question(tmp_path):
    data,folder=save_review(tmp_path)
    stem=r'پارامتر حقیقی $m$ را در نظر بگیرید. نمودار تابع $y=mx^2-3x+4$ محور افقی را در دو طرف $x=2$ قطع می‌کند. اگر حدود تغییرات این پارامتر بازهٔ $(a,b)$ باشد، مقدار $a+2b$ کدام است؟'
    data['questions'][0]['text']=stem
    row=corpus.read_json(folder/'page_00001.visual.json');row['data']=data;corpus.atomic_json(folder/'page_00001.visual.json',row)
    review=corpus.read_json(folder/'page_00001.review.json');review['data_sha256']=corpus.payload_digest(data)
    corpus.atomic_json(folder/'page_00001.review.json',review);scanning.standardize(tmp_path)
    plan=[{'name':'ریاضی','major':'riazi'}];topics=['تابع درجه دوم']
    changed=stem.replace('3x+4','7x+8').replace('x=2','x=5')
    assert style.is_source_copy(changed,plan,topics,path=tmp_path/'style-index.json')
    renamed=changed.replace('$m$','$n$').replace('mx','nx')
    assert style.is_source_copy(renamed,plan,topics,path=tmp_path/'style-index.json')
    assert not style.is_source_copy('از ریشه‌های صحیح مثبت و محدود این معادله چند مقدار پارامتر به دست می‌آید؟',plan,topics,path=tmp_path/'style-index.json')


@pytest.mark.parametrize('member',[
    'Name: unsafe.pdf\nType: Unix symbolic link\nTarget: /outside',
    'Name: directory\nType: Windows junction\nTarget: C:/outside',
    'Name: unsafe.pdf\nType: File\nHost OS: Unix\nAttributes: lrwxrwxrwx',
    'Name: unsafe.pdf\nType: File\nRedirection: hard link',
    'Name: unsafe.pdf\nType: File\nHost OS: Unix\nAttributes: prw-r--r--',
    'Name: ../outside\nType: Directory',
    'Name: safe.pdf\nType: File\n\nName: SAFE.PDF\nType: File',
    'Name: unsafe.pdf',
])
def test_unsafe_archive_members_are_rejected_before_extraction(tmp_path,monkeypatch,member):
    from types import SimpleNamespace
    source=tmp_path/'mocks';source.mkdir();(source/'source.rar').write_bytes(b'archive')
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        assert args[1]=='lt', 'Unsafe members must never reach extraction'
        return SimpleNamespace(stdout=member.encode(),returncode=0)
    monkeypatch.setattr(exam_inventory.subprocess,'run',run)
    with pytest.raises(ValueError):exam_inventory.inventory(tmp_path,tmp_path/'data',extractor='test-unrar')
    assert len(calls)==1 and not (tmp_path/'data/inventory.json').exists()


def test_regular_archive_members_preserve_sources_and_content_deduplication(tmp_path,monkeypatch):
    import pymupdf
    from types import SimpleNamespace
    source=tmp_path/'mocks';source.mkdir();pdf=source/'original.pdf'
    document=pymupdf.open();document.new_page();document.save(pdf);document.close()
    archive=source/'source.rar';archive.write_bytes(b'archive')
    listing=b'Name: folder\nType: Directory\n\nName: folder/copy.pdf\nType: File\nAttributes: ..A....\nHost OS: Windows\n'
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if args[1]=='lt':return SimpleNamespace(stdout=listing,returncode=0)
        assert args[1]=='x'
        target=Path(args[-1])/'folder/copy.pdf';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(pdf.read_bytes())
        return SimpleNamespace(stdout=b'',returncode=0)
    monkeypatch.setattr(exam_inventory.subprocess,'run',run)
    result=exam_inventory.inventory(tmp_path,tmp_path/'data',extractor='test-unrar')
    assert result=={'unique_pdfs':1,'duplicate_pdfs':1,'total_pages':1}
    assert pdf.exists() and archive.exists() and [args[1] for args in calls]==['lt','x']
    saved=corpus.read_json(tmp_path/'data/inventory.json')
    assert saved['documents'][0]['aliases'] and saved['archives'][0]['pdfs']==1


def test_existing_extraction_symlink_is_rejected_before_unrar(tmp_path,monkeypatch):
    source=tmp_path/'mocks';source.mkdir();archive=source/'source.rar';archive.write_bytes(b'archive')
    root=tmp_path/'data';destination=root/'archives'/corpus.digest(archive)
    destination.parent.mkdir(parents=True);outside=tmp_path/'outside';outside.mkdir()
    try:destination.symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('Creating directory symlinks is unavailable')
    monkeypatch.setattr(exam_inventory.subprocess,'run',lambda *a,**kw:pytest.fail('Linked target must be blocked first'))
    with pytest.raises(ValueError,match='link or junction'):exam_inventory.inventory(tmp_path,root,extractor='test-unrar')
    assert not list(outside.iterdir())


@pytest.mark.parametrize('coordinate',[10**1000,-10**1000,float('inf'),float('-inf'),float('nan'),True])
def test_invalid_numeric_bounds_fail_closed_without_overflow(coordinate):
    data=page();data['questions'][0]['bbox']=[0,0,coordinate,1]
    assert 'invalid_bbox' in scanning.validate_page(data)
    assert not scanning.agrees(data,data)


@pytest.mark.parametrize('field,value',[
    ('subject',None),('topic',{}),('id',[]),('document_name',None),('pdf_page',True),
    ('question_number','7'),('extraction_state',[]),('major_evidence',['untrusted']),('literal',[]),
    ('design',{'skills':'wrong-shape'}),
])
def test_malformed_style_rows_are_skipped_without_crashing(tmp_path,field,value):
    save_review(tmp_path);scanning.standardize(tmp_path);index=tmp_path/'style-index.json'
    data=corpus.read_json(index);data['records'][0][field]=value;corpus.atomic_json(index,data)
    assert style.references([{'name':'ریاضی','major':'riazi'}],['تابع درجه دوم'],path=index)==[]
    assert style.context([{'name':'ریاضی','major':'riazi'}],['تابع درجه دوم'],path=index)==''


@pytest.mark.parametrize('alter', ['options','bbox','design','major-evidence'])
def test_retrieval_rechecks_quality_after_valid_digest_but_bad_schema(tmp_path,alter):
    save_review(tmp_path);scanning.standardize(tmp_path);index=tmp_path/'style-index.json'
    data=corpus.read_json(index);row=data['records'][0]
    if alter=='options':row['literal']['options']=['a',{},'b','c']
    if alter=='bbox':row['literal']['bbox']=[0,0,10**1000,1]
    if alter=='design':row['design']['distractor_mechanisms']=[{}]
    if alter=='major-evidence':row['major_evidence']='گروه علوم تجربی'
    row['literal_sha256']=corpus.payload_digest(row['literal']);corpus.atomic_json(index,data)
    assert not style.references([{'name':'ریاضی','major':'riazi'}],['تابع درجه دوم'],path=index)


@pytest.mark.parametrize('plan,topics',[
    ([{'name':[],'major':'riazi'}],['تابع']),([{'name':'ریاضی','major':[]}],['تابع']),
    ([{'name':'ریاضی','majors':{'riazi':True}}],['تابع']),
    ([{'name':'ریاضی','major':'riazi'}],[{}]),([{'name':'ریاضی','major':'riazi'}],'تابع'),
])
def test_malformed_retrieval_filters_cannot_break_generation(tmp_path,plan,topics):
    assert not style.references(plan,topics,path=tmp_path/'missing.json')


def test_escaped_style_context_is_bounded_even_for_large_inferred_metadata(tmp_path):
    save_review(tmp_path);scanning.standardize(tmp_path);index=tmp_path/'style-index.json'
    data=corpus.read_json(index);row=data['records'][0]
    row['document_name']='<'*10000;row['scientific_state']='<'*10000
    for field in ('skills','distractor_mechanisms','wording_features'):row['design'][field]=['<'*1000]*5
    corpus.atomic_json(index,data)
    context=style.context([{'name':'ریاضی','major':'riazi'}],['تابع درجه دوم'],path=index)
    assert not context or len(context.split('<exam_style_data>\n')[1].split('\n</exam_style_data>')[0])<=6500


def test_standardize_skips_malformed_checkpoints_and_invalid_page_names(tmp_path):
    _,folder=save_review(tmp_path)
    corpus.atomic_json(folder/'page_bad.gemini.json',{'ok':True})
    corpus.atomic_json(folder/'page_00002.gemini.json',['malformed'])
    corpus.atomic_json(folder/'page_00002.review.json',['malformed'])
    assert scanning.standardize(tmp_path)['qualified_references']==1
    corpus.atomic_json(folder/'page_00001.review.json',['malformed review'])
    assert scanning.standardize(tmp_path)['qualified_references']==0


def test_equal_visual_record_is_not_a_third_independent_provider(tmp_path):
    _,folder=save_review(tmp_path)
    row=corpus.read_json(folder/'page_00001.visual.json')
    row['coverage']='full_page';row['prompt_digest']=scanning.PIPELINE_DIGEST
    for provider in ('visual','gemini','groq'):corpus.atomic_json(folder/f'page_00001.{provider}.json',row)
    # Remove approval without deleting the retained review checkpoint.
    corpus.atomic_json(folder/'page_00001.review.json',{'approved':False})
    assert scanning.standardize(tmp_path)['qualified_references']==1
    record=corpus.read_json(tmp_path/'style-index.json')['records'][0]
    assert record['extraction_state']=='cross_checked' and not record['human_reviewed']
    row['image']='different-page.png';corpus.atomic_json(folder/'page_00001.groq.json',row)
    assert scanning.standardize(tmp_path)['qualified_references']==0


@pytest.mark.parametrize('image',['../outside.png','/outside.png','missing.png'])
def test_cross_checked_candidates_require_safe_retained_source_image(tmp_path,image):
    _,folder=save_review(tmp_path)
    row=corpus.read_json(folder/'page_00001.visual.json')
    row.update(image=image,coverage='full_page',prompt_digest=scanning.PIPELINE_DIGEST)
    for provider in ('gemini','groq'):corpus.atomic_json(folder/f'page_00001.{provider}.json',row)
    corpus.atomic_json(folder/'page_00001.review.json',{'approved':False})
    assert scanning.standardize(tmp_path)['qualified_references']==0


def test_worker_telemetry_does_not_store_credentials_prompts_or_responses(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    f=VisionFleet([],tmp_path)
    def record():
        f.worker_update(document_name='sample.pdf',pdf_page=3,phase='requesting',
                        key='private-value',prompt='private-prompt',response='private-response')
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='exam') as executor:
        executor.submit(record).result()
    rows=f.worker_status()
    assert rows[0]['worker']=='exam_0' and rows[0]['pdf_page']==3
    assert not any(field in rows[0] for field in ('key','prompt','response'))


def test_monitor_counts_unique_retained_candidates_separately_from_full_ocr(tmp_path):
    from app.rag.exam_progress import stored_counts
    _,folder=save_review(tmp_path)
    row=corpus.read_json(folder/'page_00001.visual.json')
    row.update(coverage='full_page',prompt_digest=scanning.PIPELINE_DIGEST)
    for provider in ('gemini','groq'):corpus.atomic_json(folder/f'page_00001.{provider}.json',row)
    corpus.atomic_json(folder/'page_00002.gemini.json',{'ok':True,'data':{'questions':'bad'}})
    counts=stored_counts(tmp_path)
    assert counts['full_ocr_pages']==1
    assert counts['saved_question_candidates']==1
    row['prompt_digest']='obsolete';corpus.atomic_json(folder/'page_00001.gemini.json',row)
    corpus.atomic_json(folder/'page_00001.groq.json',row)
    assert stored_counts(tmp_path)['full_ocr_pages']==0
    # The separately visually checked source remains a retained candidate.
    assert stored_counts(tmp_path)['saved_question_candidates']==1


def test_monitor_does_not_present_stale_pid_as_active_or_waiting_as_requests(tmp_path,monkeypatch):
    from app.rag import exam_progress as monitor
    monkeypatch.setattr(monitor,'worker_alive',lambda _:True)
    monkeypatch.setattr('app.rag.exam_vision.credentials',lambda _:[])
    corpus.atomic_json(tmp_path/'scan-status.json',{'pid':1,'phase':'scanning','heartbeat':1,
        'active_candidates':3,'workers':[{'worker':'exam_0','phase':'requesting'}]})
    counts={'native_pages':0,'full_ocr_pages':0,'saved_question_candidates':0}
    s=monitor.snapshot(tmp_path,counts=counts,now=1000)
    assert not s['worker_alive'] and s['active_candidates']==0 and s['workers'][0]['phase']=='stopped'
    corpus.atomic_json(tmp_path/'coordinator-status.json',{'pid':1,'heartbeat':990,
        'phase':'waiting_for_saved_provider_retry','retry_not_before':1200})
    s=monitor.snapshot(tmp_path,counts=counts,now=1000)
    assert s['worker_alive'] and s['active_candidates']==0 and s['retry_not_before']==1200


def test_scan_publishes_actual_worker_requests_and_checkpoint_counts(tmp_path,monkeypatch):
    import time
    document={'document_id':'a'*64,'name':'sample.pdf','path':'mocks/sample.pdf','pages':2}
    corpus.atomic_json(tmp_path/'inventory.json',{'documents':[document],'archives':[]})
    monkeypatch.setattr(scanning,'pilot_tasks',lambda _:[(document,1)])
    spec=Credential('gemini','test-only-key','test-model','https://example.invalid')
    monkeypatch.setattr(scanning,'credentials',lambda _:[spec])
    def save(root,doc,p,fleet,provider):
        fleet.worker_update(phase='requesting',document_name=doc['name'],pdf_page=p)
        with fleet.lock:fleet.request_count+=1
        time.sleep(.05)
        return {'ok':True,'data':page()}
    monkeypatch.setattr(scanning,'_scan_one',save)
    monkeypatch.setattr(scanning,'standardize',lambda *_:{'qualified_references':0})
    snapshots=[]
    result=scanning.scan(tmp_path,workers=2,limit=2,provider='gemini',progress=snapshots.append)
    assert result['scanned_this_run']==2 and result['requests_this_run']==2
    assert result['active_candidates']==0 and result['pending_candidates']==0
    assert result['workers'][0]['worker'].startswith('exam_')
    assert snapshots and corpus.read_json(tmp_path/'scan-status.json')['phase']=='selected_scan_finished'


def test_smaller_groq_request_fits_observed_ceiling_without_clearing_daily_quota(tmp_path):
    import time
    spec=Credential('groq','test-only-key','qwen/test','https://example.invalid')
    f=VisionFleet([spec],tmp_path,groq_output_tokens=1000)
    f.state[spec.identity]={'request_capacity_blocked':True,'output_token_limit':1000}
    assert f.ready_count('groq')==1 and f.next_ready('groq') is not None
    f.state[spec.identity]['retry_at']=time.time()+86400
    assert f.ready_count('groq')==0
    f.state[spec.identity].pop('retry_at')
    f.state[spec.identity]['access_denied']=True
    assert f.ready_count('groq')==0 and f.next_ready('groq') is None
    f=VisionFleet([spec],tmp_path,groq_output_tokens=16384)
    f.state[spec.identity]={'request_capacity_blocked':True,'output_token_limit':1000}
    assert f.ready_count('groq')==0


def test_small_groq_budget_keeps_high_reasoning_and_rejects_truncation(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'fake png')
    def handler(request):
        body=json.loads(request.content)
        assert body['max_completion_tokens']==1000 and body['reasoning_effort']=='high'
        return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})
    spec=Credential('groq','test-only-key','qwen/test','https://example.invalid')
    f=VisionFleet([spec],tmp_path,groq_output_tokens=1000,
        client_factory=lambda _:httpx.Client(transport=httpx.MockTransport(handler)))
    assert f.request('literal transcription',image,'groq')['error']=='incomplete_transcription'


def test_imported_vm_worker_credentials_are_deduplicated_and_never_in_repr(tmp_path,monkeypatch):
    from app.rag.exam_vision import credentials
    monkeypatch.setenv('EXAM_OCR_GEMINI_MODEL','test-image-model')
    (tmp_path/'backend').mkdir()
    gem='AIza-test-only';groq='gsk_test-only'
    (tmp_path/'backend/.env').write_text('GEMINI_API_KEY='+gem+'\n')
    worker=tmp_path/'ocr-workers/worker-vm';worker.mkdir(parents=True)
    (worker/'worker.env').write_text('GEMINI_API_KEYS='+gem+','+gem+'\nGROQ_API_KEYS='+groq+'\n')
    specs=credentials(tmp_path)
    assert len(specs)==2 and specs[0].model=='test-image-model'
    assert gem not in repr(specs) and groq not in repr(specs)


def test_provider_rotation_is_independent_between_groq_and_gemini(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'fake png')
    specs=[Credential(provider,f'test-key-{provider}-{i}','test-model',
        'https://example.invalid/v1beta/openai') for provider in ('gemini','groq') for i in range(3)]
    selected=[]
    def client(spec):
        selected.append(spec.key)
        body={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]} if spec.provider=='gemini' else {'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        return httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body)))
    f=VisionFleet(specs,tmp_path,minimum_interval=0,client_factory=client)
    for _ in range(3):
        f.request('literal layout',image,'gemini');f.request('literal layout',image,'groq')
    assert selected==[f'test-key-{p}-{i}' for i in range(3) for p in ('gemini','groq')]
