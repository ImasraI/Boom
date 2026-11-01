"""Explicit new protocol for the six original drafts without blind evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import execution_lock,saved_json
from app.rag.benchmark_review import carry_verified_results
from app.rag.blind_trial import make_blind_packet,solver_prompt,parse_solver_results,compare_solver_results
from app.rag.exam_corpus import payload_digest,atomic_json
from app.rag.grounded_authoring_trial import configure_generation_client,proxy_transport_status,trial_failure_code
from scripts.carry_benchmark_verification import load_review
from scripts.solve_benchmark_blind import replay_saved_verification
from scripts.run_authoring_benchmark import available_client,capture_hook,OUT,ROOT
from scripts.run_pedagogical_pilot import request_capture,safe_bytes,now


def run(limit):
    pointer=saved_json(OUT/'review-pointer.json');current,binding,presentation=load_review(pointer['folder'])
    cp=saved_json(current/'carried-verification-pointer.json');carried=saved_json(current/cp['artifact'])
    if payload_digest(carried)!=cp['sha256']:raise ValueError('Changed carried evidence')
    previous,old_binding,old_presentation=load_review(carried['source_review'])
    matrix=carry_verified_results(old_binding,binding,old_presentation,presentation,replay_saved_verification(previous,old_presentation))
    if matrix!=carried['matrix']:raise ValueError('Carried results differ from original response replay')
    covered={r['question_id'] for r in matrix};records={r['alias']:r for r in binding['records']}
    targets=[q for q in presentation['questions'] if q['id'] not in covered]
    manifest={'schema_version':'0.1','parent_review_sha256':pointer['binding_sha256'],'carried_evidence_sha256':cp['sha256'],
      'provider':'groq','model':'openai/gpt-oss-120b','temperature':0.2,'reasoning_effort':'high','max_tokens':4096,
      'timeout_seconds':180,'targets':[{'alias':q['id'],'candidate_sha256':records[q['id']]['candidate_sha256']} for q in targets],
      'purpose':'New bounded verification; preserve all prior failures and compare only previously uncovered exact raw drafts',
      'figure_approval':False,'human_review':False,'eligible':False}
    destination=current/('remaining-verification-'+payload_digest(manifest));destination.mkdir(exist_ok=True)
    if not (destination/'manifest.json').exists():atomic_json(destination/'manifest.json',manifest)
    elif saved_json(destination/'manifest.json')!=manifest:raise ValueError('Changed verification protocol')
    from app.config import get_settings
    settings=get_settings();done=0
    with execution_lock(destination):
        for index,q in enumerate(targets):
            row=records[q['id']]
            if payload_digest(row['candidate'])!=row['candidate_sha256']:raise ValueError('Changed candidate')
            packet,mapping=make_blind_packet({'questions':[q]});prompt=solver_prompt(packet)
            b={'manifest_sha256':payload_digest(manifest),'candidate_sha256':row['candidate_sha256'],
               'packet_sha256':payload_digest(packet),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
            folder=destination/q['id'];folder.mkdir(exist_ok=True)
            prior=saved_json(folder/'state.json',None)
            if prior:
                if prior['binding']!=b:raise ValueError('Changed solver input')
                if prior['state']=='in_flight':atomic_json(folder/'state.json',{**prior,'state':'interrupted_unknown'})
                continue
            client,availability=available_client('groq',manifest['model'],0.2,settings,include_project=True,offset=index+3)
            if client is None:
                atomic_json(destination/'status.json',{'phase':'waiting_credentials','availability':availability});return
            transport=proxy_transport_status('groq')
            if not transport['reachable']:
                client.client.close();atomic_json(destination/'status.json',{'phase':'waiting_network','transport':transport});return
            configure_generation_client(client);client.minimum_completion_tokens=4096
            client.client.event_hooks['request'].append(request_capture(folder));client.client.event_hooks['response'].append(capture_hook(folder))
            atomic_json(folder/'packet.json',packet);(folder/'prompt.txt').write_bytes(prompt.encode())
            state={'state':'in_flight','binding':b,'started_at':now(),'eligible':False};atomic_json(folder/'state.json',state)
            try:
                raw=client.generate([{'role':'user','content':prompt}],max_tokens=4096,timeout=180)
                if raw:
                    data=safe_bytes(raw.encode());sha=hashlib.sha256(data).hexdigest();(folder/(sha+'.txt')).write_bytes(data)
                    parsed=parse_solver_results(raw,packet);result=compare_solver_results(parsed,mapping,presentation['solutions'])
                    report={'matrix':result,'candidate_sha256':row['candidate_sha256'],'text_only':True,'human_review':False,'eligible':False}
                    atomic_json(folder/'comparison.json',report)
                    state.update(state='compared',response_sha256=sha,comparison_sha256=payload_digest(report))
                else:state.update(state='provider_error',error_code=trial_failure_code(getattr(client,'last_error_code',''),getattr(client,'last_error','')))
            except Exception as error:state.update(state='held',error_code=type(error).__name__)
            finally:client.client.close()
            atomic_json(folder/'state.json',state);done+=1
            print(json.dumps({'alias':q['id'],'state':state['state']}),flush=True)
            if done>=limit:break
        # Reparse new original response bytes before aggregating with the carried
        # evidence. Reports and stale self-declared match flags are not trusted.
        combined=list(matrix)
        for q in targets:
            f=destination/q['id'];state=saved_json(f/'state.json',{})
            if state.get('state')!='compared':continue
            data=(f/(state['response_sha256']+'.txt')).read_bytes()
            if hashlib.sha256(data).hexdigest()!=state['response_sha256']:raise ValueError('Changed solver output')
            packet,mapping=make_blind_packet({'questions':[q]})
            result=compare_solver_results(parse_solver_results(data.decode(),packet),mapping,presentation['solutions'])
            report=saved_json(f/'comparison.json')
            if payload_digest(report)!=state['comparison_sha256'] or result!=report['matrix']:raise ValueError('Changed comparison')
            combined.extend(result)
        summary={'review_sha256':pointer['binding_sha256'],'matched':sum(r['blind_solve_state']=='matched' for r in combined),
          'disagreed':sum(r['blind_solve_state']=='disagreed' for r in combined),
          'unresolved':sum(r['blind_solve_state']=='unresolved' for r in combined),
          'without_comparison':len(presentation['questions'])-len(combined),'matrix':combined,
          'human_scientific_review':False,'figure_approval':False,'eligible':False}
        atomic_json(destination/'summary.json',summary)
        atomic_json(current/'remaining-verification-pointer.json',{'folder':destination.name,'summary_sha256':payload_digest(summary)})
        print(json.dumps({k:v for k,v in summary.items() if k not in ('matrix','review_sha256')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--max-items',type=int,default=2);args=p.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend' or not 1<=args.max_items<=6:raise ValueError('Bounded local run required')
    run(args.max_items)
