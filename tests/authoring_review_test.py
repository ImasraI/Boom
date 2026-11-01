"""Synthetic-only SR integration checks; no providers or application startup."""
import hashlib
import json
from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.auth.deps import require_admin, get_current_user
from app.rag.authoring_review import ReviewStore
from app.rag.exam_corpus import payload_digest
from app.routers.authoring_review import router, get_store

@pytest.fixture
def harness(tmp_path):
    packet_root=tmp_path/'packet';(packet_root/'crops').mkdir(parents=True)
    image=BytesIO();Image.new('RGB',(8,8),'white').save(image,format='PNG');data=image.getvalue()
    sha=hashlib.sha256(data).hexdigest();(packet_root/'crops/a.png').write_bytes(data)
    region={'image':'crops/a.png','image_sha256':sha,'pdf_page':1,'bbox':[0,0,1,1]}
    def row(id,text):
        return dict(id=id,revision=1,document_id='d'*64,exam_id='synthetic',session='one',booklet_code='A',section='math',printed_question_number=1,literal_native=text,regions=[region],source_image_sha256=[sha],content_sha256=payload_digest({'native_text':text,'regions':[region]}))
    packet={'documents':[{'document_id':'d'*64,'revision':1}],'questions':[row('q1','Synthetic question')],'answers':[row('a1','SECRET SYNTHETIC SOLUTION')],'revision':1}
    packet['answers'][0]['answer_index']=2
    def save():
        packet['packet_sha256']=payload_digest({k:v for k,v in packet.items() if k!='packet_sha256'})
        (packet_root/'packet-test.json').write_text(json.dumps(packet))
    save();(packet_root/'status.json').write_text(json.dumps({'packet':'packet-test.json'}))
    catalogue=tmp_path/'catalog.json';catalogue.write_text('{}')
    store=ReviewStore(tmp_path/'ledger',packet_root,catalogue)
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_store]=lambda:store
    client=TestClient(app)
    return client,app,store,packet,save

def admin(app,id=9):app.dependency_overrides[require_admin]=lambda:SimpleNamespace(id=id)
def url(tail=''):return '/api/authoring-review/questions/q1'+tail
def decision(packet,**changes):
    return dict(questionId='q1',binding=packet['binding'],evidenceToken=packet['evidenceToken'],dimension='editorial',decision='pass',reviewerKind='human',reviewerIdentifier='SPOOF',note='Checked against the source image',synthetic=False)|changes

def test_authorization(harness):
    client,app,*_=harness
    for path in ('/packet','/images/question'):
        assert client.get(url(path)).status_code==401
    assert client.post(url('/decisions'),json={}).status_code==401
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=2,is_admin=False)
    assert client.get(url('/packet')).status_code==403
    assert client.post(url('/blind-solve'),json={}).status_code==403

def test_blind_and_attribution(harness):
    client,app,store,*_=harness;admin(app)
    p=client.get(url('/packet')).json()
    assert p['answer'] is None and 'SECRET' not in json.dumps(p) and 'crops/' not in json.dumps(p)
    assert client.get(url('/images/answer')).status_code==404
    assert client.post(url('/decisions'),json=decision(p,dimension='science')).status_code==409
    assert client.post(url('/blind-solve'),json={'binding':p['binding'],'evidenceToken':p['evidenceToken'],'solution':'Independent synthetic derivation'}).status_code==200
    source=client.get(url('/packet?mode=source')).json()
    assert source['answer']['answer_index']==2
    assert client.post(url('/decisions'),json=decision(p,dimension='science')).status_code==200
    receipts=client.get(url('/packet?mode=source')).json()['receipts']
    assert receipts[0]['reviewerIdentifier']=='user:9'
    assert client.get(url('/packet?mode=source')).json()['eligible'] is False
    assert client.post(url('/blind-solve'),json={'binding':p['binding'],'evidenceToken':p['evidenceToken'],'solution':'Another independent derivation'}).status_code==409

@pytest.mark.parametrize('change',['catalogue','answer','question','image','packet'])
def test_stale(harness,change):
    client,app,store,packet,save=harness;admin(app)
    p=client.get(url('/packet')).json()
    if change=='catalogue':store.catalogue.write_text('{"version":2}')
    elif change=='image':(store.packet_root/'crops/a.png').write_bytes(b'changed')
    elif change=='packet':packet['revision']=2;save()
    else:packet['answers' if change=='answer' else 'questions'][0]['revision']=2;save()
    assert client.post(url('/decisions'),json=decision(p)).status_code==409

def test_malformed_and_append_only(harness):
    client,app,store,packet,save=harness;admin(app);p=client.get(url('/packet')).json()
    for changes in ({'reviewerKind':'model'},{'synthetic':True},{'note':'x'},{'dimension':'invented'}):
        assert client.post(url('/decisions'),json=decision(p,**changes)).status_code==422
    bad=decision(p);bad['binding']=dict(p['binding'],questionRevision=True)
    assert client.post(url('/decisions'),json=bad).status_code==409
    assert client.post(url('/decisions'),json=[]).status_code==422
    for value in ('pass','fail'):
        assert client.post(url('/decisions'),json=decision(p,decision=value)).status_code==200
    assert len(client.get(url('/packet?mode=source')).json()['receipts'])==2
    packet['questions'][0]['regions'][0]['image']='../outside.png';save()
    assert client.get(url('/images/question')).status_code==409

def test_packet_integrity_and_direct_answer_exposure(harness):
    client,app,store,packet,save=harness;admin(app)
    p=client.get(url('/packet')).json()
    response=client.get(url('/images/answer?mode=source&evidenceToken='+p['evidenceToken']))
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    assert client.post(url('/blind-solve'),json={'binding':p['binding'],'evidenceToken':p['evidenceToken'],'solution':'independent solution'}).status_code==409
    packet['answers'][0]['literal_native']='tampered'
    (store.packet_root/'packet-test.json').write_text(json.dumps(packet))
    assert client.get(url('/packet')).status_code==409

def test_changed_image_token_and_ambiguous_mapping(harness):
    client,app,store,packet,save=harness;admin(app)
    p=client.get(url('/packet')).json()
    assert client.get(url('/images/question?evidenceToken='+'f'*64)).status_code==409
    duplicate=dict(packet['answers'][0],id='a2');packet['answers'].append(duplicate);save()
    p=client.get(url('/packet?mode=source')).json()
    assert p['answer'] is None
    assert client.post(url('/decisions'),json=decision(p,dimension='answer_association')).status_code==409

@pytest.mark.parametrize('field,value',[('revision',True),('exam_id',None),('regions','invalid')])
def test_malformed_source_records(harness,field,value):
    client,app,store,packet,save=harness;admin(app)
    packet['questions'][0][field]=value;save()
    response=client.get(url('/packet'))
    assert response.status_code==409
    assert str(store.packet_root) not in response.text

def test_malformed_ledger_fails_closed(harness):
    client,app,store,*_=harness;admin(app)
    folder=store.root/hashlib.sha256(b'q1').hexdigest();folder.mkdir(parents=True)
    (folder/'bad.json').write_text('not JSON')
    assert client.get(url('/packet?mode=source')).status_code==409

def synthetic_candidate(store, packet):
    q=packet['questions'][0];root=store.candidate_root;root.mkdir(exist_ok=True)
    data=(store.packet_root/'crops/a.png').read_bytes();(root/'source.png').write_bytes(data)
    candidate={'schema_version':'0.1','candidate_revision':1,'question_revision':2,'question_id':q['id'],'parent_content_sha256':q['content_sha256'],'parent_image_sha256':q['source_image_sha256'],'source_document_sha256':q['document_id'],'stem':[{'kind':'text','value':'Synthetic stem '},{'kind':'math','value':'x^2=4'}],'options':[{'index':i,'text':str(i)} for i in range(4)],'source_image':{'file':'source.png','sha256':hashlib.sha256(data).hexdigest(),'pdf_page':1}}
    def save():
        candidate['candidate_sha256']=payload_digest({k:v for k,v in candidate.items() if k!='candidate_sha256'})
        name='candidate-'+candidate['candidate_sha256']+'.json'
        (root/name).write_text(json.dumps(candidate))
        (root/(hashlib.sha256(q['id'].encode()).hexdigest()+'.json')).write_text(json.dumps({'candidate':name}))
    save();return candidate,save

def test_structured_candidates_version_binding_and_safe_decisions(harness):
    client,app,store,packet,_=harness;admin(app)
    old=client.get(url('/packet')).json()
    assert client.post(url('/decisions'),json=decision(old,dimension='extraction')).status_code==409
    candidate,save=synthetic_candidate(store,packet)
    current=client.get(url('/packet')).json()
    assert current['binding']['questionRevision']==2
    assert len(current['transcription']['options'])==4
    assert 'source.png' not in json.dumps(current)
    assert current['answer'] is None
    assert client.post(url('/decisions'),json=decision(old)).status_code==409
    assert client.post(url('/decisions'),json=decision(current,dimension='extraction')).status_code==200
    blind=client.get(url('/packet')).json()
    assert len(blind['sourceChecks'])==1 and blind['answer'] is None and blind['receipts']==[]
    admin(app,id=10)
    assert client.get(url('/packet')).json()['sourceChecks']==[]
    admin(app)
    assert client.get(url('/packet')).json()['eligible'] is False
    candidate['options'][0]['text']='corrected';save()
    assert client.post(url('/decisions'),json=decision(current,dimension='extraction')).status_code==409
    assert packet['questions'][0]['revision']==1

def test_candidate_rejects_wrong_parent_and_unsafe_image(harness):
    client,app,store,packet,_=harness;admin(app)
    candidate,save=synthetic_candidate(store,packet)
    candidate['source_document_sha256']='f'*64;save()
    assert client.get(url('/packet')).status_code==409
    candidate['source_document_sha256']=packet['questions'][0]['document_id']
    candidate['source_image']['file']='../outside.png';save()
    assert client.get(url('/packet')).status_code==409

def test_bulk_preparation_resumes_without_overwriting(harness,tmp_path):
    import importlib.util
    import fitz
    script=__import__('pathlib').Path(__file__).resolve().parents[1]/'backend/scripts/prepare_review_presentations.py'
    spec=importlib.util.spec_from_file_location('prepare_review_presentations',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,app,store,packet,save=harness
    source=tmp_path/'synthetic.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((50,50),'Synthetic question');doc.save(source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    packet['documents'][0]['document_id']=digest
    for collection in ('questions','answers'):packet[collection][0]['document_id']=digest
    save()
    drafts=tmp_path/'drafts.json';drafts.write_text(json.dumps([{'number':1,'text':'Synthetic $x^2=4$','options':['1','2','3','4']}]))
    result=module.prepare(source,store.packet_root,drafts,store.candidate_root,store.catalogue)
    assert result['created']==[1] and result['human_reviews_written']==0
    before=store.current('q1')[3]
    assert module.prepare(source,store.packet_root,drafts,store.candidate_root,store.catalogue)['preserved']==[1]
    assert store.current('q1')[3]==before
    assert not list(store.root.glob('*/*.json'))
    source.write_bytes(b'wrong original')
    with pytest.raises(ValueError,match='SHA mismatch'):
        module.prepare(source,store.packet_root,drafts,store.candidate_root,store.catalogue)

def test_source_table_is_validated_and_bound_to_content(harness):
    client,app,store,packet,_=harness;admin(app)
    candidate,save=synthetic_candidate(store,packet)
    before=client.get(url('/packet')).json()
    candidate['table']={'rows':[{'label':'Synthetic intervals','cells':['0–2','2–4']},{'label':'Synthetic frequency','cells':['3','a']}]};save()
    current=client.get(url('/packet')).json()
    assert current['transcription']['table']==candidate['table']
    assert current['binding']['contentHash']!=before['binding']['contentHash']
    assert client.post(url('/decisions'),json=decision(before,dimension='extraction')).status_code==409
    candidate['table']['rows'][1]['cells'].pop();save()
    assert client.get(url('/packet')).status_code==409
