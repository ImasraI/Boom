"""Bounded local free-tier pilot; exact request bodies, no secrets or reasoning."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.authoring_benchmark import execution_lock,saved_json
from app.rag.pedagogical_authoring import parse_pedagogical_candidate,teaching_holds
from app.rag.grounded_authoring_trial import configure_generation_client,proxy_transport_status,trial_failure_code
from scripts.prepare_pedagogical_pilot import prepare,OUT,ROOT
from scripts.run_authoring_benchmark import available_client,capture_hook

FINAL={'drafted','protocol_held','provider_error','provider_refused','interrupted_unknown'}
SECRET_PATTERNS=[rb'gsk_[A-Za-z0-9]{20,}',rb'AQ\.[A-Za-z0-9_-]{35,}',rb'AIza[0-9A-Za-z_-]{30,}',rb'-----BEGIN .*PRIVATE KEY']


def now():return datetime.now(timezone.utc).isoformat()


def safe_bytes(raw):
    if any(re.search(p,raw) for p in SECRET_PATTERNS):raise ValueError('Credential-like data withheld')
    return raw


def request_capture(folder):
    events=saved_json(folder/'request-events.json',[])
    def capture(request):
        u=urlsplit(str(request.url))
        if u.scheme!='https' or u.username or u.password or u.query:raise ValueError('Unsafe request endpoint')
        body=safe_bytes(request.content)
        digest=hashlib.sha256(body).hexdigest();name='request-'+digest+'.json'
        target=folder/name
        if not target.exists():target.write_bytes(body)
        events.append({'index':len(events)+1,'method':request.method,'endpoint':u.scheme+'://'+u.netloc+u.path,
                       'body_ref':name,'body_sha256':digest,'captured_at':now(),'headers_saved':False})
        atomic_json(folder/'request-events.json',events)
    return capture


def save_return(folder,raw,state,*,recovered=False):
    data=safe_bytes(raw.encode());digest=hashlib.sha256(data).hexdigest()
    path=folder/(digest+'.txt')
    if not path.exists():path.write_bytes(data)
    result={**state,'response_sha256':digest,'recovered':recovered,'eligible':False}
    try:
        q=parse_pedagogical_candidate(raw)
        atomic_json(folder/'candidate.json',q)
        result.update(state='drafted',teaching_holds=teaching_holds(q))
    except (ValueError,TypeError) as error:
        result.update(state='protocol_held',format_error=type(error).__name__)
    atomic_json(folder/'state.json',result)
    return result


def recover(folder,state):
    if not state or state.get('state')!='in_flight':return state
    usable=[]
    for event in saved_json(folder/'transport-events.json',[]):
        if event.get('http_status')==200 and event.get('finish_reason')=='stop':
            usable.extend(f for f in event.get('fragments',[]) if f.get('kind')=='visible_content')
    if usable:
        digest=usable[-1]['sha256']
        if not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid response reference')
        data=(folder/('fragment-'+digest+'.txt')).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Saved response changed')
        return save_return(folder,data.decode('utf8'),state,recovered=True)
    state={**state,'state':'interrupted_unknown','eligible':False,'reason':'No saved complete response; no silent retry'}
    atomic_json(folder/'state.json',state)
    return state


def progress(manifest,digest,phase,**extra):
    counts={k:0 for k in sorted(FINAL)};pending=0
    for d in manifest['drafts']:
        state=saved_json(OUT/'items'/d['spec']['id']/'state.json',{})
        if state.get('state') in FINAL:counts[state['state']]+=1
        else:pending+=1
    value={'phase':phase,'protocol_sha256':digest,'updated_at':now(),'planned':len(manifest['drafts']),'pending':pending,
           'outcomes':counts,'eligible':False,**extra}
    atomic_json(OUT/'run-status.json',value)
    return value


def run(limit):
    manifest,digest=prepare()
    old=saved_json(OUT/'run-status.json',{})
    if old.get('retry_not_before',0)>time.time():
        print('Saved provider retry time has not passed. No call made.');return
    from app.config import get_settings
    settings=get_settings();done=0;transient=0
    # A process restart must not erase the provider-overload streak.
    completed=[saved_json(OUT/'items'/d['spec']['id']/'state.json',{}) for d in manifest['drafts']]
    completed=[s for s in completed if s.get('state') in FINAL]
    for state in reversed(completed):
        if state['state']!='provider_error':break
        transient+=1
    for index,draft in enumerate(manifest['drafts']):
        if (OUT/'stop-request.json').exists():progress(manifest,digest,'stopped');return
        spec=draft['spec'];folder=OUT/'items'/spec['id'];folder.mkdir(parents=True,exist_ok=True)
        prior=saved_json(folder/'state.json',None)
        if prior and prior.get('protocol_sha256')!=digest:raise ValueError('Changed item protocol')
        prior=recover(folder,prior)
        if prior:
            if prior['protocol_sha256']!=digest:raise ValueError('Changed item protocol')
            if prior.get('state') in FINAL:continue
            raise ValueError('Unknown saved item state')
        client,availability=available_client(manifest['provider'],manifest['model'],manifest['temperature'],settings,
                                            include_project=True,offset=index)
        if client is None:
            progress(manifest,digest,'waiting_credentials',availability=availability);return
        transport=proxy_transport_status('gemini')
        if not transport['reachable']:
            client.client.close();progress(manifest,digest,'waiting_network',transport=transport);return
        configure_generation_client(client)
        client.client.event_hooks['request'].append(request_capture(folder))
        client.client.event_hooks['response'].append(capture_hook(folder))
        (folder/'prompt.txt').write_bytes(draft['prompt'].encode())
        state={'state':'in_flight','protocol_sha256':digest,'prompt_sha256':draft['prompt_sha256'],
               'spec_id':spec['id'],'started_at':now(),'eligible':False}
        atomic_json(folder/'state.json',state);progress(manifest,digest,'generating',current_item=spec['id'])
        started=time.monotonic()
        try:
            raw=client.generate([{'role':'user','content':draft['prompt']}],
                                max_tokens=manifest['completion_tokens'],timeout=manifest['timeout_seconds'])
            state['elapsed_seconds']=round(time.monotonic()-started,3)
            if raw:result=save_return(folder,raw,state)
            else:
                code=trial_failure_code(getattr(client,'last_error_code',''),getattr(client,'last_error',''))
                result={**state,'state':'provider_refused' if code in ('provider_daily_quota','provider_access_denied') else 'provider_error','error_code':code}
                atomic_json(folder/'state.json',result)
        except Exception as error:
            result={**state,'state':'provider_error','error_code':type(error).__name__}
            atomic_json(folder/'state.json',result)
        finally:client.client.close()
        done+=1;status=progress(manifest,digest,'checkpoint',last_item=spec['id'])
        print(json.dumps({'spec_id':spec['id'],'outcome':result['state'],'completed':len(manifest['drafts'])-status['pending']}),flush=True)
        transient=transient+1 if result['state']=='provider_error' else 0
        if transient>=3:
            progress(manifest,digest,'waiting_provider',retry_not_before=time.time()+300);return
        if done>=limit:
            progress(manifest,digest,'completed' if status['pending']==0 else 'stopped_at_limit');return
    progress(manifest,digest,'completed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','status','stop'])
    parser.add_argument('--max-items',type=int,default=2)
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    if not 1<=args.max_items<=6:raise ValueError('Bounded run required')
    if args.action=='stop':atomic_json(OUT/'stop-request.json',{'requested_at':now()})
    elif args.action=='status':print(json.dumps(saved_json(OUT/'run-status.json',{})))
    else:
        OUT.mkdir(exist_ok=True)
        with execution_lock(OUT):run(args.max_items)
