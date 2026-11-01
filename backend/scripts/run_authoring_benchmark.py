"""Resumable free-tier paired development run. No bank, corpus or review promotion."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.authoring_benchmark import (VERSION,BenchmarkStore,execution_lock,ordered_items,
    authoring_prompt,parse_candidate,FINAL,saved_json)
from app.rag.grounded_authoring_trial import (configure_generation_client,proxy_transport_status,
    response_fragments,trial_failure_code)
from scripts.run_grounded_authoring_trial import current_inputs

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'backend/data/authoring_work/development-benchmark-v1'


def now():return datetime.now(timezone.utc).isoformat()


def load_protocol():
    status=saved_json(OUT/'status.json')
    name=status['artifact']
    if Path(name).name!=name:raise ValueError('Invalid protocol pointer')
    protocol=saved_json(OUT/name)
    if payload_digest(protocol)!=status['sha256']:raise ValueError('Frozen protocol changed')
    if payload_digest(current_inputs(2))!=protocol['source_packet_sha256']:raise ValueError('Source evidence changed')
    return protocol,status['sha256']


def candidate_keys(provider,settings,include_project=False):
    from app.rag.provider_quota import pool_gemini_generation_keys,groq_keys
    keys=pool_gemini_generation_keys(settings) if provider=='gemini' else groq_keys(settings,pool=True)
    if include_project:
        # Active envs only: never inspect credential backups or write key material.
        from app.rag.exam_vision import credentials
        keys=[*keys,*(s.key for s in credentials(ROOT) if s.provider==provider)]
    return list(dict.fromkeys(keys))


def available_client(provider,model,temperature,settings,include_project=False,offset=0):
    import httpx
    from app.rag.llm import get_llm_client,GeminiLLMClient
    from app.rag.provider_quota import (pool_gemini_generation_keys,groq_keys,
        blocked_access,blocked_quota,rate_limited)
    keys=candidate_keys(provider,settings,include_project)
    if keys:
        offset%=len(keys);keys=keys[offset:]+keys[:offset]
    scanner=saved_json(ROOT/'backend/data/exam_examples/vision-quota.json',{}) if include_project else {}
    if not isinstance(scanner,dict) or any(not isinstance(v,dict) for v in scanner.values()):
        raise ValueError('Malformed saved scanner refusal state; preserve it')
    waits=[];denied=0
    for key in keys:
        if provider=='gemini':
            candidate=GeminiLLMClient(api_key=key,base_url=settings.GEMINI_BASE_URL,model=model,
                temperature=temperature,max_tokens=16384,proxy='http://127.0.0.1:10809')
        else:
            candidate=get_llm_client(provider='groq',api_key=key,model=model)
            candidate.temperature=temperature
            old=candidate.client
            candidate.client=httpx.Client(proxy='http://127.0.0.1:10809',trust_env=False,follow_redirects=True,
                timeout=candidate.timeout,headers=dict(old.headers));old.close()
        identity=candidate._quota_identity
        access=blocked_access(identity);daily=blocked_quota(identity);minute=rate_limited(identity)
        prior=scanner.get(identity,{})
        key_sha=hashlib.sha256(key.encode()).hexdigest()
        if prior.get('access_denied') or any(v.get('http_status')==401 and v.get('key_id')==key_sha for v in scanner.values()):
            access=access or 'Saved scanner credential/model refusal'
        if prior.get('error')=='provider_daily_quota' and prior.get('retry_at',0)>time.time():
            daily=daily or (prior['retry_at'],'Saved scanner daily quota')
        if access or daily or minute:
            if access:denied+=1
            if daily:waits.append(max(1,daily[0]-time.time()))
            if minute:waits.append(minute)
            candidate.client.close();continue
        configure_generation_client(candidate)
        candidate.switch_on_rate_limit=True
        return candidate,dict(available=True)
    return None,dict(available=False,configured=len(keys),access_blocked=denied,
        retry_seconds=round(min(waits),2) if waits else None)


def capture_hook(folder):
    events=saved_json(folder/'transport-events.json',[])
    def capture(response):
        response.read()
        try:data=response.json()
        except ValueError:data={}
        fragments=[]
        for kind,text in response_fragments(data):
            sha=hashlib.sha256(text.encode()).hexdigest();target=folder/('fragment-'+sha+'.txt')
            if not target.exists():target.write_bytes(text.encode('utf8'))
            fragments.append(dict(kind=kind,sha256=sha))
        choices=data.get('choices') if isinstance(data,dict) else None
        finish=choices[0].get('finish_reason') if isinstance(choices,list) and choices and isinstance(choices[0],dict) else None
        if finish not in ('stop','length','content_filter','tool_calls'):finish=None
        usage=data.get('usage') if isinstance(data,dict) else None
        usage=({k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens')
            and type(v) is int and v>=0} if isinstance(usage,dict) else None)
        events.append(dict(http_status=response.status_code,finish_reason=finish,reported_usage=usage,
            fragments=fragments,timestamp=now(),request_headers_saved=False,reasoning_fields_saved=False))
        atomic_json(folder/'transport-events.json',events)
    return capture


def progress(store,items,phase,**extra):
    summary=store.summary(items)
    observed=unknown=0
    for item in items:
        folder=store.folder(item['item_id']);state=store.state(item['item_id'])
        events=saved_json(folder/'transport-events.json',[]);observed+=len(events)
        if state and not events:unknown+=1
    data=dict(phase=phase,updated_at=now(),**summary,observed_http_responses=observed,
        started_items_without_saved_response=unknown,**extra)
    atomic_json(OUT/'run-status.json',data)
    pointer=saved_json(OUT/'status.json')
    pointer.update(generated_items=summary['outcomes']['drafted'],provider_calls=observed,
        provider_calls_semantics='Observed authenticated HTTP responses; missing-response consumption is unknown',run_phase=phase)
    atomic_json(OUT/'status.json',pointer)
    return data


def run(provider,max_items,project_keys=False):
    from app.config import get_settings
    from app.rag.pool_usage import stage
    settings=get_settings();protocol,protocol_sha=load_protocol();items=ordered_items(protocol)
    store=BenchmarkStore(OUT)
    previous=saved_json(OUT/'run-status.json',{})
    if previous.get('phase')=='waiting_provider' and previous.get('retry_not_before',0)>time.time():
        print(json.dumps(dict(phase='waiting_provider',retry_not_before=previous['retry_not_before'])),flush=True)
        return
    saved=saved_json(OUT/'assignment.json',None)
    model=(saved['model'] if saved else settings.GEMINI_MODEL_NAME if provider=='gemini'
        else settings.POOL_LLM_MODEL_NAME or settings.LLM_MODEL_NAME)
    temperature=saved['temperature'] if saved else settings.LLM_TEMPERATURE
    assignment=dict(schema_version='0.1',protocol_sha256=protocol_sha,provider=provider,model=model,
        temperature=temperature,profile=protocol['generation_profile'],prompt_version=VERSION,
        prompt_sha256={x['item_id']:hashlib.sha256(authoring_prompt(x['task'],x['arm']).encode()).hexdigest() for x in items},
        transport_policy='Existing client retries; terminal quota/access stop; minute limit cools that credential',
        network_route='loopback_http_proxy',eligibility=False)
    store.freeze_assignment(assignment)
    if project_keys:
        atomic_json(OUT/('credential-scope-'+str(time.time_ns())+'.json'),dict(
            timestamp=now(),provider=provider,model=model,scope='active backend and OCR worker env credentials',
            configured=len(candidate_keys(provider,settings,True)),key_material_written=False,
            capacity_groups_inferred=False,authorization='User authorized other project API keys on28 October2026',
            policy='Rotate eligible slots; respect actual per-key/model quota/access evidence; no model or prompt changes'))
    for item in items:store.recover(item['item_id'])
    done_this_run=0;wait_started=None;consecutive_transient=0
    for item in items:
        prior=store.state(item['item_id'])
        if prior and prior['state'] in FINAL:continue
        while True:
            if (OUT/'stop-request.json').exists():
                progress(store,items,'stopped_at_boundary');return
            client,availability=available_client(provider,model,temperature,settings,project_keys,
                store.summary(items)['completed'] if project_keys else 0)
            if client is not None:break
            retry=availability.get('retry_seconds')
            progress(store,items,'waiting_credentials',availability=availability)
            if retry is None or retry>300:return
            if wait_started is None:wait_started=time.monotonic()
            if time.monotonic()-wait_started>600:return
            time.sleep(min(30,max(1,retry)))
        transport=proxy_transport_status(provider)
        if not transport['reachable']:
            client.client.close();progress(store,items,'waiting_network',transport=transport);return
        wait_started=None
        prompt=authoring_prompt(item['task'],item['arm'])
        binding=dict(assignment_sha256=payload_digest(assignment),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            spec_id=item['task']['spec_id'],arm=item['arm'])
        folder=store.folder(item['item_id'])
        (folder/'prompt.txt').write_bytes(prompt.encode('utf8'))
        if not store.begin(item['item_id'],binding):
            client.client.close();continue
        client.client.event_hooks['response'].append(capture_hook(folder))
        started=time.monotonic();outcome=dict(eligible=False,started_at=now())
        progress(store,items,'generating',current_item=item['item_id'])
        try:
            with stage('model_evaluation'):
                raw=client.generate([dict(role='user',content=prompt)],
                    max_tokens=assignment['profile']['completion_tokens'],
                    timeout=assignment['profile']['generate_timeout_seconds'])
            if raw:
                sha=hashlib.sha256(raw.encode()).hexdigest();(folder/(sha+'.txt')).write_bytes(raw.encode('utf8'))
                outcome['response_sha256']=sha
                try:
                    candidate=parse_candidate(raw);atomic_json(folder/'candidate.json',candidate)
                    outcome['state']='drafted'
                except (ValueError,TypeError):outcome['state']='protocol_held'
            else:
                code=trial_failure_code(getattr(client,'last_error_code',''),getattr(client,'last_error',''))
                outcome.update(error_code=code,state=('provider_refused' if code in
                    ('provider_daily_quota','provider_rate_limit','provider_access_denied') else
                    'protocol_held' if code in ('provider_json_error','provider_output_truncated') else 'provider_error'))
        except Exception as error:outcome.update(state='provider_error',error_type=type(error).__name__)
        finally:client.client.close()
        outcome['elapsed_seconds']=round(time.monotonic()-started,3)
        store.finish(item['item_id'],outcome);done_this_run+=1
        status=progress(store,items,'running')
        print(json.dumps(dict(item=item['item_id'],state=outcome['state'],completed=status['completed'],drafted=status['outcomes']['drafted'])),flush=True)
        if outcome['state']=='provider_error':
            consecutive_transient+=1
            if consecutive_transient>=3:
                progress(store,items,'waiting_provider',retry_not_before=time.time()+300);return
            time.sleep(30)
        else:consecutive_transient=0
        if done_this_run>=max_items:
            progress(store,items,'completed' if status['pending']==0 else 'stopped_at_limit');return
    progress(store,items,'completed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','status','stop'])
    parser.add_argument('--provider',choices=['gemini','groq'],default='gemini')
    parser.add_argument('--max-items',type=int,default=40)
    parser.add_argument('--project-keys',action='store_true',help='Use explicitly authorized active project env credentials, without changing frozen provider/model')
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    if not 1<=args.max_items<=40:raise ValueError('Bounded item limit required')
    if args.action=='status':print(json.dumps(saved_json(OUT/'run-status.json',{})));return
    if args.action=='stop':atomic_json(OUT/'stop-request.json',dict(requested_at=now()));return
    with execution_lock(OUT):run(args.provider,args.max_items,args.project_keys)


if __name__=='__main__':main()
