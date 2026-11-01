"""No provider/network: malformed drafts cannot cross the syntax boundary."""
import copy
import json
import pytest
from app.rag.grounded_authoring_trial import (BRIEFS, parse_drafts, prompt_for,
    proxy_transport_status, configure_generation_client, trial_failure_code,response_fragments)


def batch():
    return {'questions': [dict(brief_id=k, text='Synthetic question $x$?',
        options=['$1$', '$2$', '$3$', '$4$'], answer_index=0,
        solution='Synthetic solution; not mathematical approval.',
        design={f:'Synthetic value' for f in ('givens','unknown','domains',
            'essential_insight','structural_departure','tempting_wrong_route')}) for k in BRIEFS]}


def test_parse_preserves_raw_math_and_does_not_create_review_or_eligibility():
    value=batch()
    # Even an incorrect answer survives syntax validation; independent checking is required.
    value['questions'][0]['solution']='The answer is 999, which is absent from the options.'
    assert parse_drafts(json.dumps(value))==value
    assert not any('eligible' in q or 'human_reviewed' in q for q in value['questions'])


@pytest.mark.parametrize('mutation',[
    lambda b:b['questions'][0].update(answer_index=True),
    lambda b:b['questions'][0].update(answer_index=4),
    lambda b:b['questions'][0].update(options=['$1$']*4),
    lambda b:b['questions'][0].update(options=['$1$','$2$','$3$',' $1$ ']),
    lambda b:b['questions'][0].update(eligible=True),
    lambda b:b['questions'][0]['design'].update(tempting_wrong_route='broken '+chr(12)+'rac{a}{b}'),
    lambda b:b['questions'][0]['design'].pop('domains'),
    lambda b:b['questions'][1].update(brief_id='cubic_identity'),
    lambda b:b['questions'][1].update(brief_id='unknown'),
    lambda b:b['questions'][1].update(brief_id=[]),
    lambda b:b['questions'].pop(),
    lambda b:b.update(source_text='private'),
])
def test_malformed_drafts_rejected(mutation):
    value=copy.deepcopy(batch());mutation(value)
    with pytest.raises(ValueError):parse_drafts(json.dumps(value))


@pytest.mark.parametrize('raw', ['[]','null','{"questions":[],"questions":[]}', 'x'*64001],
                         ids=['array','null','duplicate-key','oversized'])
def test_invalid_json_shape_duplicates_and_size_held(raw):
    with pytest.raises(ValueError):parse_drafts(raw)


def test_prompt_accepts_only_known_abstract_briefs_and_no_arbitrary_source_input():
    prompt=prompt_for(list(BRIEFS))
    assert 'No difficulty labels' in prompt
    assert 'source questions' in prompt
    assert 'lesson:' not in prompt and 'question_ref' not in prompt and 'api_key' not in prompt
    with pytest.raises(ValueError):prompt_for(['private source text'])


def test_revision_two_keeps_version_one_reproducible_and_requests_real_design_changes():
    old=prompt_for(list(BRIEFS))
    revised=prompt_for(list(BRIEFS),2)
    assert revised.startswith(old) and revised!=old
    assert 'REAL existence' in revised and 'vertex correspondence' in revised
    assert 'second admissibility/counting constraint' in revised
    with pytest.raises(ValueError):prompt_for(list(BRIEFS),3)


@pytest.mark.parametrize('status',[200,401,403])
def test_transport_probe_sends_no_credentials_and_does_not_claim_key_access(monkeypatch,status):
    import httpx
    class Probe:
        def __init__(self, **kwargs):
            assert set(kwargs)=={'proxy','trust_env','timeout'}
            assert kwargs['trust_env'] is False
            assert kwargs['proxy']=='http://127.0.0.1:10809'
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def head(self,url):
            assert url=='https://generativelanguage.googleapis.com/v1beta/models'
            return httpx.Response(status)
    monkeypatch.setattr(httpx,'Client',Probe)
    assert proxy_transport_status()==dict(reachable=True,http_status=status,
        error_code=None,credentials_sent=False)


def test_transport_timeout_held_without_raw_error_details(monkeypatch):
    import httpx
    def fail(**kwargs):raise httpx.ConnectTimeout('sensitive network details')
    monkeypatch.setattr(httpx,'Client',fail)
    result=proxy_transport_status()
    assert result==dict(reachable=False,http_status=None,error_code='ConnectTimeout',credentials_sent=False)
    assert 'sensitive' not in json.dumps(result)


def test_generation_profile_reaches_actual_provider_payload_without_network():
    from app.rag.llm import GeminiLLMClient
    client=GeminiLLMClient(api_key='synthetic-not-a-credential',
        base_url='https://example.invalid',model='gemini-3.6-flash',
        temperature=.4,max_tokens=1000)
    try:
        profile=configure_generation_client(client)
        payload=client._prepare_payload([{'role':'user','content':'Synthetic example'}],max_tokens=1000)
        assert payload['reasoning_effort']=='high'
        assert payload['max_tokens']>=16384
        assert payload['response_format']=={'type':'json_object'}
        profile['reasoning_effort']='none'
        assert client.reasoning_effort=='high'
    finally:
        client.client.close()


@pytest.mark.parametrize('reason,expected',[
    ('HTTP 503 (private response details)','provider_unavailable'),
    ('HTTP 403','provider_access_denied'),('HTTP 404','provider_model_unavailable'),
    ('HTTP 429','provider_rate_limit'),('timeout','provider_timeout'),
    ('[SSL: UNEXPECTED_EOF_WHILE_READING]','provider_transport_error'),
    ('empty completion','provider_empty_response')])
def test_error_classification_excludes_raw_details(reason,expected):
    assert trial_failure_code('',reason)==expected
    assert trial_failure_code('provider_daily_quota',reason)=='provider_daily_quota'


def test_fragment_capture_only_retains_visible_generation_not_reasoning_or_error_details():
    body={'error':{'message':'private upstream details','failed_generation':'{invalid draft'},
        'choices':[{'message':{'content':'visible draft','reasoning':'hidden reasoning'}}],
        'headers':{'Authorization':'synthetic-secret'}}
    result=response_fragments(body)
    assert result==[('failed_generation','{invalid draft'),('visible_content','visible draft')]
    assert 'hidden reasoning' not in json.dumps(result) and 'synthetic-secret' not in json.dumps(result)
    assert response_fragments({'choices':[None,{}, {'message':None}]})==[]
