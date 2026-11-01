"""One local answer-withheld solver trial; no source corpus, bank or review writes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.blind_trial import make_blind_packet,solver_prompt,parse_solver_results,compare_solver_results
from app.rag.grounded_authoring_trial import configure_generation_client,proxy_transport_status,trial_failure_code,response_fragments
from scripts.run_grounded_authoring_trial import current_inputs

ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'backend/data/authoring_work/grounded-authoring-trial-v1/attempt-10'
REVIEW=PARENT/'review-v1'
OUT=PARENT/'blind-solve-v1'


def inputs():
    status=json.loads((REVIEW/'presentation-status.json').read_text())
    presentation=json.loads((REVIEW/'prepared-presentation.json').read_text(encoding='utf8'))
    if payload_digest(presentation)!=status['payload_sha256']:raise ValueError('Presentation changed')
    for file,field in [('questions.html','questions_html_sha256'),('solutions.html','solutions_html_sha256')]:
        if hashlib.sha256((REVIEW/file).read_bytes()).hexdigest()!=status[field]:raise ValueError('Reviewed page changed')
    checks=json.loads((PARENT/status['check_artifact']).read_text(encoding='utf8'))
    if payload_digest(checks)!=status['check_sha256']:raise ValueError('Math report changed')
    if payload_digest(current_inputs(2))!=checks['source_packet_sha256']:raise ValueError('Source evidence changed')
    feedback_status=json.loads((REVIEW/'editorial-status.json').read_text())
    feedback=json.loads((REVIEW/feedback_status['artifact']).read_text(encoding='utf8'))
    if (payload_digest(feedback)!=feedback_status['sha256'] or feedback['reviewer_kind']!='human'
            or feedback['presentation_payload_sha256']!=status['payload_sha256']):raise ValueError('Editorial feedback stale')
    packet,mapping=make_blind_packet(presentation)
    binding=dict(schema_version='0.1',presentation_sha256=status['payload_sha256'],
        check_sha256=status['check_sha256'],editorial_feedback_sha256=feedback_status['sha256'],
        blind_packet_sha256=payload_digest(packet),local_alias_mapping=mapping,
        solver_mode='text_only_blind',figure_independently_evaluated=False)
    return presentation,packet,binding


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','solve'])
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    presentation,packet,binding=inputs()
    OUT.mkdir(exist_ok=True)
    if args.action=='prepare':
        for prefix,data in [('blind-packet',packet),('binding',binding)]:
            path=OUT/(prefix+'-'+payload_digest(data)+'.json')
            if not path.exists():atomic_json(path,data)
        print(json.dumps(dict(status='prepared',questions=len(packet['questions']),answers_withheld=True,provider_calls=0)))
        return
    if (OUT/'status.json').exists():raise ValueError('Preserve existing solver attempt')
    from app.config import get_settings
    from app.rag.llm import get_llm_client
    from app.rag.provider_quota import groq_keys,blocked_access,blocked_quota,rate_limited
    from app.rag.pool_usage import stage
    import httpx
    settings=get_settings();model=settings.POOL_LLM_MODEL_NAME or settings.LLM_MODEL_NAME
    if (settings.POOL_LLM_PROVIDER or settings.LLM_PROVIDER).lower()!='groq':
        raise ValueError('This separate-solver pilot requires the existing free-tier Groq configuration')
    client=None
    for key in groq_keys(settings,pool=True):
        candidate=get_llm_client(provider='groq',api_key=key,model=model)
        if blocked_access(candidate._quota_identity) or blocked_quota(candidate._quota_identity) or rate_limited(candidate._quota_identity):
            candidate.client.close();continue
        old=candidate.client
        candidate.client=httpx.Client(proxy='http://127.0.0.1:10809',trust_env=False,follow_redirects=True,
            timeout=candidate.timeout,headers=dict(old.headers))
        old.close();client=candidate;break
    if client is None:raise ValueError('No currently available configured solver credential')
    profile=configure_generation_client(client)
    state=dict(status='started',provider='groq',model=model,binding_sha256=payload_digest(binding),
        blind_packet_sha256=payload_digest(packet),profile=profile,answers_withheld=True,
        maximum_generate_calls=1,eligible=False,human_scientific_review=False)
    atomic_json(OUT/'status.json',state)
    started=time.monotonic();events=[]
    def capture(response):
        response.read()
        try:data=response.json()
        except ValueError:data={}
        fragments=[]
        for kind,text in response_fragments(data):
            sha=hashlib.sha256(text.encode()).hexdigest()
            path=OUT/('fragment-'+sha+'.txt')
            if not path.exists():path.write_bytes(text.encode('utf8'))
            fragments.append(dict(kind=kind,sha256=sha))
        usage=data.get('usage') if isinstance(data,dict) else None
        usage=({k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens')
                and type(v) is int and v>=0} if isinstance(usage,dict) else None)
        events.append(dict(http_status=response.status_code,fragments=fragments,reported_usage=usage))
        atomic_json(OUT/'transport-events.json',events)
    client.client.event_hooks['response'].append(capture)
    try:
        transport=proxy_transport_status('groq');state['transport']=transport
        if not transport['reachable']:
            state['error_code']='proxy_transport_unavailable';raise ValueError('Proxy unavailable')
        with stage('model_evaluation'):
            raw=client.generate([dict(role='user',content=solver_prompt(packet))],
                max_tokens=profile['completion_tokens'],timeout=profile['generate_timeout_seconds'])
        if not raw:
            state['error_code']=trial_failure_code(getattr(client,'last_error_code',''),getattr(client,'last_error',''))
            raise ValueError('No solver output')
        digest=hashlib.sha256(raw.encode()).hexdigest()
        (OUT/(digest+'.txt')).write_bytes(raw.encode('utf8'));state['response_sha256']=digest
        results=parse_solver_results(raw,packet)
        _,_,current=inputs()
        if current!=binding:raise ValueError('Candidate evidence changed during solving')
        matrix=compare_solver_results(results,binding['local_alias_mapping'],presentation['solutions'])
        report=dict(schema_version='0.1',binding_sha256=payload_digest(binding),response_sha256=digest,
            matrix=matrix,matched=sum(r['blind_solve_state']=='matched' for r in matrix),
            disagreed=sum(r['blind_solve_state']=='disagreed' for r in matrix),
            unresolved=sum(r['blind_solve_state']=='unresolved' for r in matrix),
            eligibility=False,limitations=['Model agreement is supporting evidence, not scientific or human approval',
                'Text-only blind solve; diagram not supplied','Small three-item development pilot'])
        name='comparison-'+payload_digest(report)+'.json';atomic_json(OUT/name,report)
        state.update(status='compared',comparison_artifact=name,comparison_sha256=payload_digest(report),
            matched=report['matched'],disagreed=report['disagreed'],unresolved=report['unresolved'])
    except Exception as error:
        state.update(status='held',error_type=type(error).__name__)
    state['elapsed_seconds']=round(time.monotonic()-started,3)
    state['last_success_usage']=client.last_usage._asdict()
    client.client.close();atomic_json(OUT/'status.json',state)
    print(json.dumps(state))


if __name__=='__main__':main()
