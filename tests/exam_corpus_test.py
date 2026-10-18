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


def literal_page():
    data=page()
    for q in data['questions']:
        for field in ('subject','topic','design'):q.pop(field)
        q['options']=[{'label':i,'text':text} for i,text in enumerate(q['options'],1)]
        q['figure_labels']=[]
    return data


def annotation():
    return {k:page()['questions'][0][k] for k in ('subject','topic','design')}


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


def test_atomic_checkpoint_retries_transient_windows_reader_conflict(tmp_path,monkeypatch):
    target=tmp_path/'status.json';corpus.atomic_json(target,{'old':True})
    replace=corpus.os.replace;calls=[];waits=[]
    def temporarily_locked(source,dest):
        calls.append(dest)
        if len(calls)<3:
            assert corpus.read_json(target)=={'old':True}
            raise PermissionError('sharing violation')
        return replace(source,dest)
    monkeypatch.setattr(corpus.os,'replace',temporarily_locked)
    monkeypatch.setattr(corpus.time,'sleep',waits.append)
    corpus.atomic_json(target,{'new':True})
    assert corpus.read_json(target)=={'new':True} and len(calls)==3
    assert waits==[.025,.05] and list(tmp_path.glob('*.tmp'))==[]


def test_atomic_checkpoint_keeps_old_data_on_persistent_permission_failure(tmp_path,monkeypatch):
    target=tmp_path/'status.json';corpus.atomic_json(target,{'old':True})
    calls=[]
    def locked(source,dest):
        calls.append(dest);raise PermissionError('persistent denial')
    monkeypatch.setattr(corpus.os,'replace',locked)
    monkeypatch.setattr(corpus.time,'sleep',lambda delay:None)
    with pytest.raises(PermissionError):corpus.atomic_json(target,{'new':True})
    assert len(calls)==7 and corpus.read_json(target)=={'old':True}
    assert list(tmp_path.glob('*.tmp'))==[]


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


def test_rejected_truncated_reply_keeps_token_cost_and_finish_reason_without_content(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'image')
    def handler(request):
        return httpx.Response(200,json={'candidates':[{'finishReason':'MAX_TOKENS',
            'content':{'parts':[{'thought':True,'text':'hidden reasoning'},{'text':'unfinished literal source'}]}}],
            'usageMetadata':{'promptTokenCount':123,'candidatesTokenCount':20,
                'thoughtsTokenCount':980,'totalTokenCount':1123,'unexpected':'sensitive-value'}})
    f,_=fleet(tmp_path,handler);result=f.request('transcribe',image)
    assert not result['ok'] and result['error']=='incomplete_transcription'
    assert result['finish_reason']=='MAX_TOKENS' and result['usage']['thoughtsTokenCount']==980
    assert all(value not in json.dumps(result) for value in ('hidden reasoning','unfinished literal source','sensitive-value'))


def test_free_copying_mode_preserves_high_effort_for_annotations(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'image');payloads=[]
    spec=Credential('groq','private-test-key','qwen/qwen3.8-27b','https://example.test/v1')
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
    f=VisionFleet([spec],tmp_path,minimum_interval=0,groq_output_tokens=1000,groq_reasoning_effort='none',
        client_factory=lambda _:httpx.Client(transport=httpx.MockTransport(handler)))
    assert f.request('copy',image,'groq')['ok']
    assert f.request_annotation('classify',image,'groq')['ok']
    assert [p['reasoning_effort'] for p in payloads]==['none','high']
    assert all(p['max_completion_tokens']==1000 for p in payloads)


def test_system_vpn_route_explicitly_overrides_stale_env_proxy(tmp_path,monkeypatch):
    from app.rag.exam_vision import credentials
    backend=tmp_path/'backend';backend.mkdir()
    (backend/'.env').write_text('GEMINI_API_KEY=AQ.test-key\nEXAM_OCR_PROXY=http://127.0.0.1:10809\n',encoding='utf-8')
    monkeypatch.setenv('EXAM_OCR_PROXY','system')
    rows=credentials(tmp_path)
    assert len(rows)==1 and rows[0].proxy==''


def test_overloaded_model_cools_down_without_marking_other_keys_quota_exhausted(tmp_path,monkeypatch):
    from app.rag import exam_vision
    image=tmp_path/'image.png';image.write_bytes(b'image');calls=[]
    specs=[Credential('gemini',f'test-key-{i}','gemini-3.8-flash','https://example.test/v1beta/openai') for i in range(2)]
    def handler(request):
        calls.append(request)
        if len(calls)==1:return httpx.Response(503,json={'error':{'message':'High demand'}})
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]})
    monkeypatch.setattr(exam_vision.random,'uniform',lambda *_:0)
    f=VisionFleet(specs,tmp_path,minimum_interval=0,client_factory=lambda _:httpx.Client(transport=httpx.MockTransport(handler)))
    assert f.request('copy',image,'gemini')['http_status']==503
    assert f.request('copy',image,'gemini')['error']=='no_ready_credentials' and len(calls)==1
    assert specs[1].identity not in f.state
    assert f.health()[1]['service_overloaded']
    assert f.next_ready('gemini')>=__import__('time').time()+29
    reloaded=VisionFleet(specs,tmp_path)
    assert reloaded.health()[1]['service_overloaded']
    f.services[f._service_id(specs[0])]['retry_at']=0
    assert f.request('copy',image,'gemini')['ok'] and len(calls)==2
    assert not f.services


def test_all_literals_survive_annotation_quota_and_count_only_as_candidates(tmp_path,monkeypatch):
    from app.rag import exam_progress,exam_transcription
    doc={'document_id':'a'*64,'name':'source.pdf'};image=tmp_path/'image.png';image.write_bytes(b'image')
    folder=tmp_path/'documents'/doc['document_id']/'vision/page_00001'
    monkeypatch.setattr(scanning,'layout_input',lambda *args:[image])
    monkeypatch.setattr(scanning,'question_input',lambda *args:([image],None,''))
    first=literal_page();second=literal_page();second['questions'][0]['number']=8
    layout={'page_kind':'questions','source_major':'riazi','major_evidence':first['major_evidence'],
            'question_numbers':[7,8],'complete':True,'uncertainties':[]}
    class Fleet:
        def __init__(self):self.rows=iter([layout,first,second]);self.order=[]
        def request(self,prompt,*args):
            self.order.append('literal');return {'ok':True,'data':next(self.rows),'model':'test-model'}
        def request_annotation(self,*args):
            self.order.append('annotation');return {'ok':False,'error':'provider_daily_quota'}
    f=Fleet();r=scanning.structured_scan(tmp_path,folder,image,f,'groq',doc,1)
    assert r['error']=='provider_daily_quota' and f.order==['literal']*3+['annotation']
    saved=corpus.read_json(folder.parent/'page_00001.groq.literal.json')
    assert saved['expected_question_numbers']==[7,8] and not saved['human_reviewed']
    counts=exam_progress.stored_counts(tmp_path)
    assert counts['full_ocr_pages']==1 and counts['saved_question_candidates']==2
    assert scanning.standardize(tmp_path)['qualified_references']==0
    saved['expected_question_numbers']=[7,8,9]
    corpus.atomic_json(folder.parent/'page_00001.groq.literal.json',saved)
    assert exam_progress.stored_counts(tmp_path)['full_ocr_pages']==0


def test_uncertain_first_question_does_not_prevent_saving_next_literal(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'image')
    first=literal_page();first['questions'][0]['uncertainties']=['unclear sign']
    second=literal_page();second['questions'][0]['number']=8
    layout={'page_kind':'questions','source_major':'riazi','major_evidence':first['major_evidence'],
            'question_numbers':[7,8],'complete':True,'uncertainties':[]}
    class Fleet:
        def __init__(self):self.rows=iter([layout,first,second]);self.calls=0
        def request(self,*args):
            self.calls+=1;return {'ok':True,'data':next(self.rows),'model':'test'}
    f=Fleet();folder=tmp_path/'parts-folder'
    result=scanning.structured_scan(tmp_path,folder,image,f,'groq')
    assert result['error']=='invalid_question_transcription' and f.calls==3
    assert result['completed_questions']==1 and result['question_failures'][0]['number']==7
    assert any(any(q['number']==8 for q in corpus.read_json(p)['data'].get('questions',[]))
               for p in (folder/'parts').glob('*.json'))


def test_reviewed_page_requires_entire_coverage_and_matching_source_hash(tmp_path):
    from app.rag.exam_review import reviewed_page
    image=tmp_path/'image.png';image.write_bytes(b'original source')
    row={'ok':True,'document_id':'a'*64,'pdf_page':1,'coverage':'full_page','image':'image.png','data':page()}
    review={'approved':True,'review_kind':'visual','reviewer':'assistant','reviewed_questions':[7],
            'page_coverage_checked':True,'expected_question_numbers':[7],
            'data_sha256':corpus.payload_digest(row['data']),'image_sha256':corpus.digest(image)}
    corpus.atomic_json(tmp_path/'record.json',row);corpus.atomic_json(tmp_path/'review.json',review)
    corpus.atomic_json(tmp_path/'reviewed-page.json',{'record':'record.json','review':'review.json'})
    assert reviewed_page(tmp_path)
    review['expected_question_numbers']=[7,8];corpus.atomic_json(tmp_path/'review.json',review)
    assert reviewed_page(tmp_path) is None
    review['expected_question_numbers']=[7];corpus.atomic_json(tmp_path/'review.json',review)
    image.write_bytes(b'changed source')
    assert reviewed_page(tmp_path) is None


def test_review_view_escapes_source_and_does_not_claim_automatic_or_scientific_approval(tmp_path):
    from app.rag.exam_review import review_html
    image=tmp_path/'image.png';image.write_bytes(b'original source')
    data=page();data['questions'][0]['text']='<script>alert("unsafe")</script> متن سؤال'
    row={'ok':True,'document_id':'a'*64,'pdf_page':1,'coverage':'full_page','image':'image.png','data':data}
    review={'approved':True,'review_kind':'visual','reviewed_questions':[7],'page_coverage_checked':True,
            'expected_question_numbers':[7],'data_sha256':corpus.payload_digest(data),'image_sha256':corpus.digest(image)}
    for name,value in [('record.json',row),('review.json',review),('reviewed-page.json',{'record':'record.json','review':'review.json'})]:corpus.atomic_json(tmp_path/name,value)
    result=review_html(tmp_path)
    assert '<script>' not in result and '&lt;script&gt;' in result
    assert 'خروجی کاملاً خودکار نیست' in result and 'بازبینی علمی یا تأیید انسانی انجام نشده' in result
    row['data']['questions'][0]['options'].reverse();corpus.atomic_json(tmp_path/'record.json',row)
    assert review_html(tmp_path) is None


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
            data=layout if prompt==scanning.LAYOUT_PROMPT else annotation() if prompt.startswith(scanning.ANNOTATION_PROMPT) else literal_page()
            return {'ok':True,'data':data,'model':'stub'}
    f=Stub();image=tmp_path/'image.png';image.write_bytes(b'png')
    r=scanning.structured_scan(tmp_path,tmp_path/'scan',image,f,'groq')
    assert r['ok'] and len(r['data']['questions'])==1 and f.calls==3
    assert scanning.structured_scan(tmp_path,tmp_path/'scan',image,f,'groq')['ok'] and f.calls==3
    layout['question_numbers']=[True]
    assert not scanning.validate_layout(layout)


@pytest.mark.parametrize('value,expected', [('۷',7),('٧',7),('7',7),('۸۷',87),
    ('1.5','1.5'),('-7','-7'),('7e1','7e1'),(True,True),(['7'],['7'])])
def test_only_structural_digit_ids_are_normalized(value,expected):
    from app.rag.exam_transcription import normalize_identifiers
    raw={'question_numbers':[value], 'marker_question_numbers':[None,value],
        'questions':[{'number':value,'text':'۵۰μs و ۶/۲۸√۳',
                      'options':[{'label':value,'text':'۳۳ گرم'}]}]}
    before=copy.deepcopy(raw);result=normalize_identifiers(raw)
    assert result['question_numbers']==[expected] and result['marker_question_numbers']==[None,expected]
    assert result['questions'][0]['number']==expected
    assert result['questions'][0]['options'][0]=={'label':expected,'text':'۳۳ گرم'}
    assert result['questions'][0]['text']=='۵۰μs و ۶/۲۸√۳' and raw==before


def test_unsupported_track_is_unknown_with_claim_preserved_not_qualified():
    from app.rag.exam_transcription import canonical_candidate
    raw={'page_kind':'questions','question_numbers':['۸۷'],'complete':True,
         'uncertainties':[],'source_major':'tajrobi','major_evidence':'دوازدهم ریاضی'}
    data=canonical_candidate(raw)
    assert data['source_major'] is None and data['major_evidence']==raw['major_evidence']
    assert data['metadata_warnings'][0]['claimed_value']=='tajrobi'
    assert scanning.validate_layout(data) and raw['source_major']=='tajrobi'
    assert not scanning.validate_layout({**data,'complete':False})
    assert not scanning.validate_layout({**data,'uncertainties':['missing options']})
    assert not scanning.validate_layout({**data,'question_numbers':['۸۷',87]})
    assert not scanning.validate_layout({**data,'question_numbers':[[]]})
    assert not scanning.validate_layout({**data,'uncertainties':None})


def test_cached_persian_layout_ids_resume_without_repeating_provider_call(tmp_path):
    layout={'page_kind':'questions','question_numbers':['۷'],'complete':True,
        'uncertainties':[],'source_major':'riazi','major_evidence':'دهم ریاضی'}
    folder=tmp_path/'scan';file=folder/'parts'/('groq.'+corpus.payload_digest(scanning.LAYOUT_PROMPT)+'.json')
    raw={'ok':True,'data':layout};corpus.atomic_json(file,raw)
    literal=literal_page();literal['source_major']='riazi';literal['major_evidence']='دهم ریاضی'
    literal['questions'][0]['number']='۷'
    for option in literal['questions'][0]['options']:option['label']=str(option['label'])
    class Fleet:
        calls=[]
        def request(self,prompt,image,provider):
            self.calls.append(prompt)
            assert prompt!=scanning.LAYOUT_PROMPT
            return {'ok':True,'data':annotation() if prompt.startswith(scanning.ANNOTATION_PROMPT) else literal}
    fleet=Fleet();result=scanning.structured_scan(tmp_path,folder,tmp_path/'image.png',fleet,'groq')
    assert result['ok'] and len(fleet.calls)==2 and result['data']['source_major'] is None
    assert result['data']['questions'][0]['number']==7 and result['data']['metadata_warnings']
    assert corpus.read_json(file)==raw


def test_question_budget_fallback_preserves_crop_and_layout_metadata(tmp_path,monkeypatch):
    doc={'document_id':'a'*64,'name':'source.pdf'};image=tmp_path/'source.png';image.write_bytes(b'image')
    heading=tmp_path/'heading.png';heading.write_bytes(b'heading')
    aid='\n<untrusted_native_reading_aid>optional PDF spans</untrusted_native_reading_aid>'
    monkeypatch.setattr(scanning,'layout_input',lambda *args:[image])
    monkeypatch.setattr(scanning,'question_input',lambda *args:([image,heading],
        {'bbox_pdf':[0,0,100,100],'dimensions':[100,100]},aid))
    layout={'page_kind':'questions','source_major':'riazi','major_evidence':page()['major_evidence'],
        'question_numbers':[7],'complete':True,'uncertainties':[]}
    literal=literal_page();literal.update(source_major=None,major_evidence='')
    class Fleet:
        calls=[]
        def request(self,prompt,images,provider):
            self.calls.append((prompt,images))
            if prompt==scanning.LAYOUT_PROMPT:return {'ok':True,'data':layout}
            assert images==[image]
            if prompt.startswith(scanning.ANNOTATION_PROMPT):return {'ok':True,'data':annotation()}
            if aid in prompt:return {'ok':False,'error':'request_input_too_large','http_status':413}
            return {'ok':True,'data':literal}
    fleet=Fleet();folder=tmp_path/'scan'
    result=scanning.structured_scan(tmp_path,folder,image,fleet,'groq',doc,1)
    assert result['ok'] and result['data']['source_major']=='riazi'
    assert len(fleet.calls)==4 and sum(aid in prompt for prompt,_ in fleet.calls)==1
    assert result['data']['questions'][0]['text']==literal['questions'][0]['text']
    assert scanning.structured_scan(tmp_path,folder,image,fleet,'groq',doc,1)['ok']
    assert len(fleet.calls)==4  # Known oversize payload and successful parts both resume locally.


def test_input_size_error_does_not_block_key_for_smaller_payload(tmp_path):
    spec=Credential('groq','test-only-key','qwen/test','https://example.invalid')
    image=tmp_path/'source.png';image.write_bytes(b'image');calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1:return httpx.Response(413,json={'error':{'message':
            'Request too large on input tokens per minute: Limit 7000, Requested 7500'}})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop',
            'message':{'content':json.dumps(page())}}]})
    fleet=VisionFleet([spec],tmp_path,minimum_interval=0,
        client_factory=lambda _:httpx.Client(transport=httpx.MockTransport(handler)))
    result=fleet.request('oversize',image,'groq')
    assert result['error']=='request_input_too_large' and result['request_scoped']
    assert fleet.ready_count('groq')==1 and not fleet.health()[0]['access_denied']
    assert fleet.request('small',image,'groq')['ok'] and len(calls)==2


@pytest.mark.parametrize('message,temporary', [
    ('Access denied. Please check your network settings.',True),
    ('You do not have permission to use this model.',False)])
def test_network_403_is_distinct_from_credential_permission_denial(tmp_path,message,temporary):
    import time
    spec=Credential('groq','test-only-key','qwen/test','https://example.invalid')
    image=tmp_path/'source.png';image.write_bytes(b'image')
    fleet=VisionFleet([spec],tmp_path,minimum_interval=0,client_factory=lambda _:httpx.Client(
        transport=httpx.MockTransport(lambda request:httpx.Response(403,json={'error':{'message':message}}))))
    result=fleet.request('copy',image,'groq')
    assert (result['error']=='provider_network_denied') is temporary
    assert fleet.health()[0]['access_denied'] is (not temporary)
    if temporary:assert fleet.next_ready('groq')>=time.time()+299
    else:assert fleet.next_ready('groq') is None


def test_legacy_network_refusal_reclassified_only_by_worker_preserving_other_blocks(tmp_path):
    import time
    spec=Credential('groq','test-only-key','qwen/test','https://example.invalid')
    saved={spec.identity:{'http_status':403,'error':'provider_access_denied','access_denied':True,
        'detail':'Access denied. Please check your network settings.'},
        'other':{'http_status':401,'access_denied':True,'detail':'Invalid API Key'},
        'daily':{'error':'provider_daily_quota','retry_at':time.time()+86400}}
    corpus.atomic_json(tmp_path/'vision-quota.json',saved)
    fleet=VisionFleet([spec],tmp_path)
    assert corpus.read_json(tmp_path/'vision-quota.json')==saved  # Monitor construction is read-only.
    assert fleet.reclassify_network_refusals()==1
    result=corpus.read_json(tmp_path/'vision-quota.json')
    assert result['other']==saved['other'] and result['daily']==saved['daily']
    assert not result[spec.identity]['access_denied'] and result[spec.identity]['retry_at']>time.time()
    assert result[spec.identity]['previous_classification']=='provider_access_denied'
    assert fleet.reclassify_network_refusals()==0


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
    assert stored_counts(tmp_path)['retained_full_ocr_pages']==1
    # The separately visually checked source remains a retained candidate.
    assert stored_counts(tmp_path)['saved_question_candidates']==1


def test_changed_pipeline_keeps_valid_old_page_when_new_provider_attempt_fails(tmp_path,monkeypatch):
    from app.rag.exam_progress import stored_counts
    doc={'document_id':'a'*64,'name':'exam.pdf'}
    path=tmp_path/'documents'/doc['document_id']/'vision/page_00001.gemini.json'
    old={'ok':True,'data':page(),'document_id':doc['document_id'],'pdf_page':1,
         'coverage':'full_page','prompt_digest':'old-version'}
    corpus.atomic_json(path,old)
    monkeypatch.setattr(scanning,'image_for',lambda *args:tmp_path/'image.png')
    monkeypatch.setattr(scanning,'structured_scan',lambda *args:{'ok':False,'error':'provider_daily_quota'})
    scanning._scan_one(tmp_path,doc,1,object(),'gemini')
    archive=list((path.parent/'retained').glob('*/*.json'))
    assert len(archive)==1 and corpus.read_json(archive[0])==old
    assert corpus.read_json(path)['error']=='provider_daily_quota'
    counts=stored_counts(tmp_path)
    assert counts['full_ocr_pages']==0 and counts['retained_full_ocr_pages']==1
    assert counts['saved_question_candidates']==1


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


def test_finished_benchmark_is_distinct_from_an_interrupted_scanner(tmp_path,monkeypatch):
    from app.rag import exam_progress as monitor
    monkeypatch.setattr(monitor,'worker_alive',lambda _:False)
    monkeypatch.setattr('app.rag.exam_vision.credentials',lambda _:[])
    saved={'pid':1,'phase':'selected_scan_finished','heartbeat':150,'selected_pages':30,
           'active_candidates':0,'pending_candidates':0,'quarantined_candidates':6,'scanned_this_run':24}
    corpus.atomic_json(tmp_path/'scan-status.json',saved)
    state=monitor.snapshot(tmp_path,counts={},now=1000)
    assert state['phase']=='benchmark_complete' and not state['worker_alive']
    assert state['held_candidates']==6 and state['saved_this_run']==24
    assert state['batch_saved_candidates']==24
    corpus.atomic_json(tmp_path/'scan-status.json',{**saved,'scanned_this_run':0,'stored_candidates':24})
    resumed=monitor.snapshot(tmp_path,counts={'retained_full_ocr_pages':26},now=1000)
    assert resumed['batch_saved_candidates']==24 and resumed['saved_this_run']==0
    assert resumed['retained_full_ocr_pages']==26
    corpus.atomic_json(tmp_path/'scan-status.json',{**saved,'phase':'scanning','pending_candidates':20})
    assert monitor.snapshot(tmp_path,counts={},now=1000)['phase']=='stopped'


def test_scan_dispatch_shares_slots_and_fills_unavailable_provider_capacity():
    names=('gemini','groq')
    pending={name:list(range(30)) for name in names}
    order=scanning.dispatch_providers(names,pending,{},dict.fromkeys(names,13),8)
    assert order==['gemini','groq']*4
    assert scanning.dispatch_providers(names,pending,{}, {'gemini':0,'groq':16},8)==['groq']*8
    active={i:(None,None,'gemini') for i in range(3)}
    assert scanning.dispatch_providers(names,pending,active,dict.fromkeys(names,13),8)==[
        'groq','groq','groq','gemini','groq']
    pending['groq']=[1]
    order=scanning.dispatch_providers(names,pending,{},dict.fromkeys(names,13),8)
    assert len(order)==8 and order.count('groq')==1 and order.count('gemini')==7
    assert scanning.dispatch_providers(names,pending,active,dict.fromkeys(names,13),2)==[]


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


def test_scan_batch_offset_selects_new_pages_without_revisiting_old_ones(tmp_path,monkeypatch):
    document={'document_id':'a'*64,'name':'sample.pdf','path':'mocks/sample.pdf','pages':4}
    corpus.atomic_json(tmp_path/'inventory.json',{'documents':[document],'archives':[]})
    monkeypatch.setattr(scanning,'pilot_tasks',lambda _:[(document,1)])
    monkeypatch.setattr(scanning,'credentials',lambda _:[Credential('gemini','test-only-key','test-model','https://example.invalid')])
    selected=[]
    def save(root,doc,p,fleet,provider):
        selected.append(p)
        return {'ok':True,'data':page()}
    monkeypatch.setattr(scanning,'_scan_one',save)
    monkeypatch.setattr(scanning,'standardize',lambda *_:{'qualified_references':0})
    result=scanning.scan(tmp_path,workers=2,limit=2,offset=2,provider='gemini')
    assert sorted(selected)==[3,4]
    assert result['selected_offset']==2 and result['selected_pages']==2


def test_next_batch_does_not_skip_unfinished_work():
    import importlib.util
    path=Path(__file__).resolve().parents[1]/'backend/scripts/import_exam_examples.py'
    spec=importlib.util.spec_from_file_location('exam_batch_driver',path)
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    assert driver.next_batch_offset({'phase':'selected_scan_finished','selected_pages':30})==30
    assert driver.next_batch_offset({'phase':'selected_scan_finished','selected_pages':30,'selected_offset':30})==60
    for previous in ({'phase':'waiting_for_credentials','selected_pages':30},
                     {'phase':'selected_scan_finished','selected_pages':30,'pending_candidates':1},
                     {'phase':'selected_scan_finished','selected_pages':0},
                     {'phase':'selected_scan_finished','selected_pages':30,'selected_offset':-1}):
        with pytest.raises(ValueError):driver.next_batch_offset(previous)


def test_restart_resumes_current_batch_instead_of_resetting_to_zero():
    import importlib.util
    path=Path(__file__).resolve().parents[1]/'backend/scripts/import_exam_examples.py'
    spec=importlib.util.spec_from_file_location('exam_resume_driver',path)
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    assert driver.resume_batch_offset({'selected_offset':90})==90
    assert driver.resume_batch_offset({'selected_offset':90},explicit=0)==0
    assert driver.resume_batch_offset({})==0
    with pytest.raises(ValueError):driver.resume_batch_offset({'selected_offset':-1})


def test_proxy_loss_mid_batch_pauses_with_saved_pages_and_pending_queue(tmp_path,monkeypatch):
    from app.rag import exam_network
    document={'document_id':'a'*64,'name':'sample.pdf','path':'mocks/sample.pdf','pages':2}
    corpus.atomic_json(tmp_path/'inventory.json',{'documents':[document],'archives':[]})
    monkeypatch.setattr(scanning,'pilot_tasks',lambda _:[(document,1)])
    spec=Credential('gemini','test-only-key','test-model','https://example.invalid',proxy='http://127.0.0.1:10809')
    monkeypatch.setattr(scanning,'credentials',lambda _:[spec])
    online=[True];selected=[]
    monkeypatch.setattr(exam_network,'scan_network',lambda *_:{'ready':online[0]})
    def save(root,doc,p,fleet,provider):
        selected.append(p);online[0]=False
        return {'ok':True,'data':page()}
    monkeypatch.setattr(scanning,'_scan_one',save)
    monkeypatch.setattr(scanning,'standardize',lambda *_:{'qualified_references':0})
    result=scanning.scan(tmp_path,workers=1,limit=2,offset=0,provider='gemini')
    assert selected==[1]
    assert result['phase']=='waiting_for_network' and result['pending_candidates']==1
    assert result['scanned_this_run']==1 and result['quarantined_candidates']==0
    assert result['waiting_for_local_proxy'] is True
    assert corpus.read_json(tmp_path/'documents'/('a'*64)/'vision/page_00001.gemini.json')['ok'] is True


def test_connection_reset_is_paused_without_clearing_another_key_daily_quota(tmp_path):
    import httpx,time
    live=Credential('gemini','test-live','test-model','https://example.invalid')
    limited=Credential('gemini','test-limited','test-model','https://example.invalid')
    class Disconnected:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def post(self,*_,**__):raise httpx.ConnectError('simulated connection reset')
    fleet=VisionFleet([live,limited],tmp_path,client_factory=lambda _:Disconnected())
    saved={'error':'provider_daily_quota','daily_quota':True,'retry_at':time.time()+3600}
    fleet.state[limited.identity]=dict(saved)
    image=tmp_path/'input.png';image.write_bytes(b'image')
    before=time.time();result=fleet.request('OCR',image,'gemini')
    assert result['error']=='provider_or_transport_error' and result['network_error']
    assert result['retryable'] and before<result['retry_at']<=before+35
    assert fleet.state[limited.identity]==saved and not fleet.busy


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


def test_structured_scan_does_not_reuse_invalid_cached_layout(tmp_path):
    folder=tmp_path/'page';parts=folder/'parts';parts.mkdir(parents=True)
    corpus.atomic_json(parts/('gemini.'+corpus.payload_digest(scanning.LAYOUT_PROMPT)+'.json'),
        {'ok':True,'data':{'page_kind':'questions','complete':False,'question_numbers':[7],'uncertainties':['cut off']}})
    calls=[]
    class Fleet:
        def request(self,prompt,image,provider):
            calls.append(prompt)
            if prompt.startswith(scanning.ANNOTATION_PROMPT):return {'ok':True,'data':annotation()}
            return {'ok':True,'data':{'page_kind':'questions','complete':True,'question_numbers':[7],
                'source_major':'riazi','major_evidence':'گروه علوم ریاضی و فنی','uncertainties':[]}} if prompt==scanning.LAYOUT_PROMPT else {'ok':True,'data':literal_page()}
    result=scanning.structured_scan(tmp_path,folder,tmp_path/'image.png',Fleet(),'gemini')
    assert result['ok'] and len(calls)==3 and calls[0]==scanning.LAYOUT_PROMPT


def test_design_annotation_cannot_rewrite_literal_or_claim_review(tmp_path):
    from app.rag.exam_transcription import valid_annotation
    good=annotation()
    assert valid_annotation(good)
    for key,value in [('text','rewritten'),('options',['wrong']),('human_reviewed',True),('answer_index',0)]:
        assert not valid_annotation({**good,key:value})


def test_literal_checkpoint_survives_design_provider_refusal(tmp_path):
    calls=[]
    class Fleet:
        refused=False
        def request(self,prompt,image,provider):
            calls.append(prompt)
            if prompt==scanning.LAYOUT_PROMPT:
                return {'ok':True,'data':{'page_kind':'questions','complete':True,'question_numbers':[7],
                    'source_major':'riazi','major_evidence':page()['major_evidence'],'uncertainties':[]}}
            if prompt.startswith(scanning.ANNOTATION_PROMPT):
                if not self.refused:
                    self.refused=True;return {'ok':False,'error':'provider_daily_quota','retry_at':123}
                return {'ok':True,'data':annotation()}
            return {'ok':True,'data':literal_page()}
    fleet=Fleet();folder=tmp_path/'parts'
    assert scanning.structured_scan(tmp_path,folder,tmp_path/'image.png',fleet,'groq')['error']=='provider_daily_quota'
    result=scanning.structured_scan(tmp_path,folder,tmp_path/'image.png',fleet,'groq')
    assert result['ok'] and len(calls)==4
    assert result['data']['questions'][0]['text']==page()['questions'][0]['text']
    assert result['data']['questions'][0]['options']==page()['questions'][0]['options']


@pytest.mark.parametrize('labels',[[1,2,3,3],[1,3,2,4],[True,2,3,4]])
def test_literal_options_reject_duplicate_reordered_or_boolean_labels(labels):
    data=literal_page()
    for row,label in zip(data['questions'][0]['options'],labels):row['label']=label
    assert 'incomplete_options' in scanning.validate_page(data,require_annotations=False,labelled_options=True)


def test_original_region_render_and_source_bbox_projection(tmp_path):
    import pymupdf
    from app.rag.exam_transcription import project_bbox
    pdf=pymupdf.open();pdf.new_page(width=120,height=180);source=tmp_path/'source.pdf';pdf.save(source);pdf.close()
    target=tmp_path/'region.png'
    corpus.render_region(source,1,target,[0,30,120,90],72)
    metadata=corpus.read_json(target.with_suffix('.render.json'))
    assert metadata['bbox_pdf']==[0,30,120,90] and metadata['source_sha256']==corpus.digest(source)
    assert project_bbox([0,0,1,1],{'bbox_pdf':[0,30,120,90],'dimensions':[120,180]})==[0,1/6,1,.5]
    with pytest.raises(ValueError):corpus.render_region(source,1,target,[0,0,121,180])


def test_literal_only_candidates_are_visible_without_inferred_annotations(tmp_path):
    from app.rag.exam_progress import stored_counts
    folder=tmp_path/'documents'/('a'*64)/'vision/page_00001/parts';folder.mkdir(parents=True)
    corpus.atomic_json(folder/'groq.literal.json',{'ok':True,'data':literal_page()})
    counts=stored_counts(tmp_path)
    assert counts['saved_question_candidates']==1 and counts['full_ocr_pages']==0


def test_ambiguous_or_malformed_native_markers_fall_back_to_original_image(tmp_path):
    from app.rag.exam_transcription import question_input
    doc={'document_id':'a'*64,'path':'mocks/source.pdf'}
    file=corpus.native_path(tmp_path,doc['document_id'],1)
    corpus.atomic_json(file,['bad cache'])
    image=tmp_path/'original.png'
    assert question_input(tmp_path,doc,1,7,image)==([image],None,'')
    row={'document_id':doc['document_id'],'pdf_page':1,'dimensions':[120,180],'blocks':[
        {'bbox':[0,10,120,30],'lines':[{'bbox':[0,10,120,20],'spans':[{'text':'7- first'}]}]},
        {'bbox':[0,80,120,100],'lines':[{'bbox':[0,80,120,90],'spans':[{'text':'7- second'}]}]}]}
    corpus.atomic_json(file,row)
    images,region,aid=question_input(tmp_path,doc,1,7,image)
    assert images==[image] and region is None and 'fallible' in aid


def test_marker_reading_aid_keeps_the_original_page_and_source_coordinates(tmp_path,monkeypatch):
    import pymupdf
    from app.rag import exam_transcription as transcriber
    pdf=pymupdf.open();page=pdf.new_page(width=595,height=842)
    page.insert_text((500,140),'-7 question',fontsize=12)
    page.insert_text((500,240),'-8 question',fontsize=12)
    source=tmp_path/'source.pdf';pdf.save(source);pdf.close()
    doc={'document_id':corpus.digest(source),'path':'source.pdf'}
    image=tmp_path/'original.png'
    corpus.render_page(source,1,image)
    monkeypatch.setattr(transcriber,'safe_path',lambda *_:source)
    inputs=transcriber.layout_input(doc,1,image)
    assert len(inputs)==2 and inputs[1]==image
    record=corpus.read_json(inputs[0].with_suffix('.render.json'))
    assert record['purpose']=='reading_aid_only' and len(record['source_regions_pdf'])==2
    assert transcriber.layout_input(doc,1,image)==inputs


def test_retry_wait_survives_deadline_crossing_during_status_write(tmp_path,monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    path=Path(__file__).resolve().parents[1]/'backend/scripts/import_exam_examples.py'
    spec=importlib.util.spec_from_file_location('exam_retry_driver',path)
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    clock=iter([.999,1.001,1.002]);sleeps=[]
    monkeypatch.setattr(driver,'time',SimpleNamespace(time=lambda:next(clock),sleep=sleeps.append))
    monkeypatch.setattr(driver,'credential_files_signature',lambda _:())
    driver.wait_for_scan_retry(tmp_path,1,limit=7,provider='auto')
    assert sleeps==[0]
    saved=corpus.read_json(tmp_path/'coordinator-status.json')
    assert saved['retry_not_before']==1 and saved['phase']=='waiting_for_saved_provider_retry'


def test_network_preflight_deduplicates_proxies_without_publishing_them(monkeypatch):
    from app.rag import exam_network
    specs=[Credential('gemini','key-a','model','https://example.test',proxy='http://user:private@localhost:99'),
           Credential('groq','key-b','model','https://example.test',proxy='http://user:private@localhost:99')]
    calls=[]
    def probe(proxy):calls.append(proxy);return False
    monkeypatch.setattr(exam_network,'proxy_available',probe)
    status=exam_network.scan_network(specs)
    assert not status['ready'] and status['affected_credentials']==2 and len(calls)==1
    assert 'private' not in json.dumps(status) and 'key-a' not in json.dumps(status)
    specs.append(Credential('gemini','key-c','model','https://example.test',proxy=''))
    monkeypatch.setattr(exam_network,'proxy_available',lambda proxy:not proxy)
    assert exam_network.scan_network(specs)['ready']


def test_network_wait_recovers_without_erasing_saved_quota(tmp_path,monkeypatch):
    import importlib.util
    from app.rag import exam_network,exam_vision
    path=Path(__file__).resolve().parents[1]/'backend/scripts/import_exam_examples.py'
    spec=importlib.util.spec_from_file_location('exam_network_driver',path)
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    monkeypatch.setattr(exam_vision,'credentials',lambda _:[])
    states=iter([{'ready':False,'affected_credentials':2,'unreachable_proxy_providers':['gemini']},{'ready':True}])
    monkeypatch.setattr(exam_network,'scan_network',lambda *_:next(states))
    sleeps=[];monkeypatch.setattr(driver.time,'sleep',sleeps.append)
    corpus.atomic_json(tmp_path/'vision-quota.json',{'refused':{'retry_at':123456}})
    assert driver.wait_for_scan_network(tmp_path,limit=7,provider='auto',watch=True)
    assert sleeps==[5]
    assert corpus.read_json(tmp_path/'coordinator-status.json')['phase']=='waiting_for_network'
    assert corpus.read_json(tmp_path/'vision-quota.json')=={'refused':{'retry_at':123456}}


def test_monitor_reports_live_network_wait_instead_of_provider_cooldown(tmp_path,monkeypatch):
    from app.rag import exam_progress
    monkeypatch.setattr(exam_progress,'worker_alive',lambda _:True)
    monkeypatch.setattr('app.rag.exam_vision.credentials',lambda _:[])
    corpus.atomic_json(tmp_path/'coordinator-status.json',{'pid':1,'heartbeat':990,'phase':'waiting_for_network'})
    state=exam_progress.snapshot(tmp_path,counts={},now=1000)
    assert state['worker_alive'] and state['network_blocked']
    assert state['phase']=='waiting_for_network' and state['active_candidates']==0


def test_retry_wait_wakes_for_new_credentials_without_resetting_quota(tmp_path,monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    path=Path(__file__).resolve().parents[1]/'backend/scripts/import_exam_examples.py'
    spec=importlib.util.spec_from_file_location('exam_credentials_driver',path)
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    clock=iter([0,1,2]);sleeps=[];signatures=iter([('old',),('old',),('new',)])
    monkeypatch.setattr(driver,'time',SimpleNamespace(time=lambda:next(clock),sleep=sleeps.append))
    monkeypatch.setattr(driver,'credential_files_signature',lambda _:next(signatures))
    corpus.atomic_json(tmp_path/'vision-quota.json',{'saved-key':{'retry_at':100}})
    driver.wait_for_scan_retry(tmp_path,100,limit=7,provider='auto')
    assert sleeps==[30] and corpus.read_json(tmp_path/'vision-quota.json')['saved-key']['retry_at']==100


def test_monitor_distinguishes_eligible_keys_from_quarantined_provider_work(tmp_path,monkeypatch):
    from app.rag import exam_progress as monitor
    monkeypatch.setattr(monitor,'worker_alive',lambda _:True)
    monkeypatch.setattr('app.rag.exam_vision.credentials',lambda _:[Credential('groq','test-key','test-model','https://example.invalid')])
    corpus.atomic_json(tmp_path/'scan-status.json',{'pid':1,'heartbeat':990,'phase':'waiting_for_credentials',
        'pending_by_provider':{'groq':0},'quarantined_by_provider':{'groq':7}})
    result=monitor.snapshot(tmp_path,counts={},now=1000)['providers'][0]
    assert not result['blocked'] and result['pending_pages']==0 and result['held_pages']==7
    assert result['work_state']=='no eligible pilot pages · held for review'


def test_fleet_uses_another_key_while_first_key_waits_for_daily_reset(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'fake png')
    specs=[Credential('gemini',f'test-key-{i}','test-model','https://example.invalid/v1beta/openai') for i in range(2)]
    used=[]
    def client(spec):
        used.append(spec.key)
        body={'error':{'message':'Daily request quota exceeded'}} if spec==specs[0] else {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]}
        return httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(429 if spec==specs[0] else 200,json=body)))
    f=VisionFleet(specs,tmp_path,minimum_interval=0,client_factory=client)
    assert f.request('literal layout',image,'gemini')['error']=='provider_daily_quota'
    assert f.request('literal layout',image,'gemini')['ok']
    assert f.request('literal layout',image,'gemini')['ok']
    assert used==['test-key-0','test-key-1','test-key-1']


def test_question_and_heading_images_are_sent_as_separate_source_parts(tmp_path):
    import base64
    first=tmp_path/'question.png';first.write_bytes(b'question image')
    second=tmp_path/'heading.png';second.write_bytes(b'heading image')
    def handler(request):
        body=json.loads(request.content)
        parts=body['contents'][0]['parts']
        assert len(parts)==3
        assert [base64.b64decode(p['inlineData']['data']) for p in parts[1:]]==[b'question image',b'heading image']
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]})
    f,_=fleet(tmp_path,handler)
    assert f.request('literal question',[first,second],'gemini')['ok']
    with pytest.raises(ValueError):f.request('literal question',[first]*4,'gemini')


def test_gemini_25_pro_uses_supported_maximum_thinking_budget(tmp_path):
    image=tmp_path/'image.png';image.write_bytes(b'fake png')
    def handler(request):
        config=json.loads(request.content)['generationConfig']
        assert config['thinkingConfig']=={'thinkingBudget':32768,'includeThoughts':False}
        assert config['maxOutputTokens']==65536 and 'mediaResolution' not in config
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]})
    f,_=fleet(tmp_path,handler,model='gemini-2.5-pro')
    assert f.request('literal image',image,'gemini')['ok']


@pytest.mark.parametrize('model,expected', [
    ('gemini-3.5-flash-lite',{'thinkingLevel':'MINIMAL','includeThoughts':False}),
    ('gemini-3.8-flash',{'thinkingLevel':'LOW','includeThoughts':False}),
    ('gemini-2.5-flash-lite',{'thinkingBudget':0,'includeThoughts':False})])
def test_efficient_gemini_profile_never_requests_high_thinking(tmp_path,monkeypatch,model,expected):
    monkeypatch.setenv('EXAM_OCR_GEMINI_THINKING','minimal')
    monkeypatch.setenv('EXAM_OCR_GEMINI_OUTPUT_TOKENS','8192')
    image=tmp_path/'image.png';image.write_bytes(b'fake png')
    def handler(request):
        config=json.loads(request.content)['generationConfig']
        assert config['thinkingConfig']==expected and config['maxOutputTokens']==8192
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]})
    f,_=fleet(tmp_path,handler,model=model)
    assert f.request('literal page',image,'gemini')['ok']


def test_changing_model_or_thinking_profile_does_not_reuse_other_models_outputs(tmp_path):
    layout={'page_kind':'questions','source_major':'riazi','major_evidence':page()['major_evidence'],
        'question_numbers':[7],'complete':True,'uncertainties':[]}
    class Fleet:
        specs=[Credential('gemini','test-key','model-a','https://example.invalid')]
        gemini_thinking_level='minimal';gemini_output_tokens=8192;calls=0
        def request(self,prompt,image,provider):
            self.calls+=1
            data=layout if prompt==scanning.LAYOUT_PROMPT else annotation() if prompt.startswith(scanning.ANNOTATION_PROMPT) else literal_page()
            return {'ok':True,'data':data,'model':self.specs[0].model}
    f=Fleet();folder=tmp_path/'scan';image=tmp_path/'image.png'
    assert scanning.structured_scan(tmp_path,folder,image,f,'gemini')['ok'] and f.calls==3
    assert scanning.structured_scan(tmp_path,folder,image,f,'gemini')['ok'] and f.calls==3
    f.specs=[Credential('gemini','test-key','model-b','https://example.invalid')]
    assert scanning.structured_scan(tmp_path,folder,image,f,'gemini')['ok'] and f.calls==6
    f.gemini_thinking_level='low'
    assert scanning.structured_scan(tmp_path,folder,image,f,'gemini')['ok'] and f.calls==9
    assert len(list((folder/'parts').glob('*.json')))==9


@pytest.mark.parametrize('empty', [False,True])
def test_whole_page_method_uses_one_call_and_keeps_quality_gate(tmp_path,monkeypatch,empty):
    doc={'document_id':'a'*64,'name':'source.pdf'};image=tmp_path/'image.png';image.write_bytes(b'png')
    monkeypatch.setattr(scanning,'image_for',lambda *args:image)
    class Fleet:
        scan_method='whole-page';calls=0
        def request(self,prompt,source,provider):
            self.calls+=1;assert source==image and prompt==scanning.WHOLE_PAGE_PROMPT
            data=literal_page()
            if empty:data['questions']=[]
            return {'ok':True,'data':data,'model':'test-model'}
    f=Fleet();result=scanning._scan_one(tmp_path,doc,1,f,'gemini')
    assert f.calls==1 and result['ok'] is (not empty)
    assert result['quality_review_state']=='unreviewed_model_candidate'
    if empty:assert 'questions_missing' in result['issues']


def test_whole_page_literal_schema_constrains_format_without_approving_source(tmp_path,monkeypatch):
    monkeypatch.setenv('EXAM_OCR_GEMINI_THINKING','minimal')
    image=tmp_path/'image.png';image.write_bytes(b'png')
    def handler(request):
        config=json.loads(request.content)['generationConfig'];schema=config['responseJsonSchema']
        assert config['thinkingConfig']['thinkingLevel']=='MINIMAL'
        assert schema['properties']['source_major']['enum']==['riazi','tajrobi','ensani',None]
        question=schema['properties']['questions']['items']['properties']
        assert question['bbox']['items']=={'type':'number','minimum':0,'maximum':1}
        assert 'ordered_tokens' in question['options']['items']['required']
        assert 'subject' not in question and 'design' not in question
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP',
            'content':{'parts':[{'text':json.dumps(literal_page())}]}}]})
    f,_=fleet(tmp_path,handler,model='gemini-3.5-flash-lite')
    assert f.request_literal_page(scanning.WHOLE_PAGE_PROMPT,image)['ok']


def test_ambiguous_rtl_option_sequences_are_held_even_when_json_is_valid():
    data=literal_page();q=data['questions'][0]
    q['options'][0]['text']='B و B و A'
    assert 'ambiguous_option_sequence' in scanning.validate_page(data,require_annotations=False,labelled_options=True)
    q['options'][0].update(ordered_tokens=['A','B','B'],visual_tokens_left_to_right=['B','B','A'])
    assert not scanning.validate_page(data,require_annotations=False,labelled_options=True)
    q['options'][0]['ordered_tokens']=['A','A','B']
    assert 'ambiguous_option_sequence' in scanning.validate_page(data,require_annotations=False,labelled_options=True)


def test_auto_network_uses_known_vpn_listener_when_present(monkeypatch):
    from app.rag import exam_network
    calls=[]
    monkeypatch.setattr(exam_network,'proxy_available',lambda proxy:calls.append(proxy) or True)
    assert exam_network.default_proxy()=='http://127.0.0.1:10809' and len(calls)==1
    monkeypatch.setattr(exam_network,'proxy_available',lambda proxy:False)
    assert exam_network.default_proxy()==''


def test_request_ledger_counts_actual_attempts_without_source_or_key(tmp_path,monkeypatch):
    monkeypatch.setenv('EXAM_OCR_GEMINI_THINKING','minimal')
    image=tmp_path/'image.png';image.write_bytes(b'private-image-content')
    def handler(request):
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP',
            'content':{'parts':[{'text':'{}'}]}}],'usageMetadata':{'promptTokenCount':12,'totalTokenCount':15}})
    f,spec=fleet(tmp_path,handler,model='gemini-3.5-flash-lite');f.minimum_interval=20
    assert f.request('private-source-text',image,'gemini')['ok']
    assert f.request('private-source-text',image,'gemini')['error']=='no_ready_credentials'
    text=(tmp_path/'vision-requests.jsonl').read_text(encoding='utf-8')
    assert all(secret not in text for secret in ('private-source-text','private-image-content',spec.key))
    events=[json.loads(line) for line in text.splitlines()]
    assert [e['event'] for e in events]==['attempt_started','attempt_finished']
    assert events[0]['request_id']==events[1]['request_id']
    assert events[1]['http_status']==200 and events[1]['usage']['totalTokenCount']==15
    assert events[0]['thinking']=='minimal' and not f.audit_error


def test_efficiency_review_is_source_bound_and_escapes_untrusted_candidate(tmp_path,monkeypatch):
    from app.rag import exam_review
    source={'review':{'image_sha256':'a'*64},'record':{'data':page()}}
    monkeypatch.setattr(exam_review,'reviewed_page',lambda _:source)
    folder=tmp_path/'model-probe/efficient-whole-page/gemini-3.5-flash-lite'
    report={'source_image_sha256':'a'*64,'reference_data_sha256':corpus.payload_digest(page()),
        'model':'test-model','checks':[{'item':'<script>unsafe()</script>','result':'fail'}]}
    candidate=literal_page();candidate['questions'][0]['text']='<script>source()</script>'
    corpus.atomic_json(folder/'quality-review.json',report)
    corpus.atomic_json(folder/'page16-literal-schema.json',{'source_image_sha256':'a'*64,'data':candidate})
    html=exam_review.efficient_pilot_html(tmp_path)
    assert 'NOT approved for unattended scanning' in html and '<script>' not in html
    assert '&lt;script&gt;source()' in html and '&lt;script&gt;unsafe()' in html
    corpus.atomic_json(folder/'quality-review.json',{**report,'reference_data_sha256':'changed'})
    assert exam_review.efficient_pilot_html(tmp_path) is None
