"""Offline checkpoint and request-capture checks with synthetic data."""
import hashlib
import json
import httpx
import pytest
from scripts.run_pedagogical_pilot import request_capture,recover,save_return,safe_bytes
from scripts.run_authoring_benchmark import capture_hook


def test_actual_request_body_is_saved_exactly_without_auth_header(tmp_path):
    body=b'{"model":"synthetic","messages":[{"role":"user","content":"x"}]}'
    req=httpx.Request('POST','https://example.invalid/chat/completions',content=body,
                      headers={'Authorization':'Bearer synthetic-private-value'})
    request_capture(tmp_path)(req)
    events=json.loads((tmp_path/'request-events.json').read_text())
    assert len(events)==1 and events[0]['headers_saved'] is False
    assert (tmp_path/events[0]['body_ref']).read_bytes()==body
    assert events[0]['body_sha256']==hashlib.sha256(body).hexdigest()
    assert all(b'synthetic-private-value' not in p.read_bytes() for p in tmp_path.iterdir())


@pytest.mark.parametrize('url',['http://example.invalid/chat','https://user:password@example.invalid/chat','https://example.invalid/chat?key=secret'])
def test_unsafe_capture_endpoints_fail_before_persisting(tmp_path,url):
    with pytest.raises(ValueError):request_capture(tmp_path)(httpx.Request('POST',url,content=b'{}'))
    assert list(tmp_path.iterdir())==[]


def test_credentials_in_request_body_fail_closed(tmp_path):
    raw=('gsk_'+'a'*40).encode()
    with pytest.raises(ValueError):safe_bytes(raw)
    with pytest.raises(ValueError):request_capture(tmp_path)(httpx.Request('POST','https://example.invalid',content=raw))
    assert list(tmp_path.iterdir())==[]


def test_hidden_reasoning_and_provider_headers_not_persisted(tmp_path):
    response=httpx.Response(200,json={'choices':[{'message':{'content':'{"synthetic":true}',
                         'reasoning':'SYNTHETIC_PRIVATE_REASONING'},'finish_reason':'stop'}],
                         'usage':{'prompt_tokens':12,'completion_tokens':8,'total_tokens':20}},
                         headers={'Authorization':'synthetic-response-secret'})
    capture_hook(tmp_path)(response)
    data=b''.join(p.read_bytes() for p in tmp_path.iterdir())
    assert b'SYNTHETIC_PRIVATE_REASONING' not in data and b'synthetic-response-secret' not in data
    assert json.loads((tmp_path/'transport-events.json').read_text())[0]['reported_usage']['total_tokens']==20


def test_unknown_interrupted_consumption_is_not_automatically_retried(tmp_path):
    state={'state':'in_flight','protocol_sha256':'synthetic','eligible':False}
    result=recover(tmp_path,state)
    assert result['state']=='interrupted_unknown' and result['eligible'] is False
    assert recover(tmp_path,result)==result


def test_invalid_saved_fragment_hash_cannot_be_recovered(tmp_path):
    sha='a'*64
    (tmp_path/'transport-events.json').write_text(json.dumps([{'http_status':200,'finish_reason':'stop',
        'fragments':[{'kind':'visible_content','sha256':sha}]}]))
    (tmp_path/('fragment-'+sha+'.txt')).write_text('not the saved digest')
    with pytest.raises(ValueError):recover(tmp_path,{'state':'in_flight'})


def test_malformed_response_is_preserved_without_becoming_a_question(tmp_path):
    result=save_return(tmp_path,'{"wrong_schema":true}',{'protocol_sha256':'synthetic'})
    assert result['state']=='protocol_held' and result['eligible'] is False
    assert (tmp_path/(result['response_sha256']+'.txt')).read_text()=='{"wrong_schema":true}'
    assert not (tmp_path/'candidate.json').exists()


def test_completed_response_recovery_preserves_failure_instead_of_reissuing(tmp_path):
    raw='{"wrong_schema":true}';sha=hashlib.sha256(raw.encode()).hexdigest()
    (tmp_path/('fragment-'+sha+'.txt')).write_text(raw)
    (tmp_path/'transport-events.json').write_text(json.dumps([{'http_status':200,'finish_reason':'stop',
        'fragments':[{'kind':'visible_content','sha256':sha}]}]))
    result=recover(tmp_path,{'state':'in_flight','protocol_sha256':'synthetic'})
    assert result['state']=='protocol_held' and result['recovered'] is True


def test_progress_uses_frozen_run_size_instead_of_original_six(tmp_path,monkeypatch):
    from scripts import run_pedagogical_pilot as runner
    monkeypatch.setattr(runner,'OUT',tmp_path)
    manifest={'drafts':[{'spec':{'id':'synthetic_a'}},{'spec':{'id':'synthetic_b'}}]}
    value=runner.progress(manifest,'synthetic_digest','prepared')
    assert value['planned']==2 and value['pending']==2 and value['eligible'] is False


def test_provider_recovery_freezes_new_run_without_changing_parent(tmp_path,monkeypatch):
    from scripts import run_pedagogical_recovery as recovery
    from app.rag.exam_corpus import atomic_json,payload_digest
    original=tmp_path/'original';original.mkdir()
    out=tmp_path/'recovery'
    monkeypatch.setattr(recovery,'ORIGINAL',original);monkeypatch.setattr(recovery,'OUT',out)
    parent={'drafts':[{'spec':{'id':name},'prompt':'synthetic unchanged prompt'} for name in recovery.TARGETS],
            'evidence':[{'spec_id':name,'synthetic':True} for name in recovery.TARGETS]}
    sha=payload_digest(parent);atomic_json(original/('protocol-'+sha+'.json'),parent)
    atomic_json(original/'pointer.json',{'file':'protocol-'+sha+'.json','sha256':sha})
    for name in recovery.TARGETS:
        folder=original/'items'/name;folder.mkdir(parents=True)
        atomic_json(folder/'state.json',{'state':'provider_error','eligible':False})
    before={str(p):p.read_bytes() for p in original.rglob('*') if p.is_file()}
    manifest,digest=recovery.prepare()
    assert manifest['planned_items']==2 and manifest['parent_protocol_sha256']==sha
    assert manifest['drafts']==parent['drafts'] and manifest['original_outcomes_preserved'] is True
    assert recovery.prepare()==(manifest,digest)
    assert before=={str(p):p.read_bytes() for p in original.rglob('*') if p.is_file()}
