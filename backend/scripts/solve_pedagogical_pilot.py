"""Independent answer-withheld solving of saved v2 drafts; bounded free calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import execution_lock,saved_json
from app.rag.blind_trial import make_blind_packet,solver_prompt,parse_solver_results,compare_solver_results
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.grounded_authoring_trial import configure_generation_client,proxy_transport_status,trial_failure_code
from app.rag.pedagogical_authoring import parse_pedagogical_candidate
from scripts.prepare_pedagogical_pilot import OUT,ROOT
from scripts.run_authoring_benchmark import available_client,capture_hook
from scripts.run_pedagogical_pilot import request_capture,safe_bytes,now


def solve(limit):
    pointer=saved_json(OUT/'pointer.json');protocol=saved_json(OUT/pointer['file'])
    if payload_digest(protocol)!=pointer['sha256']:raise ValueError('Changed authoring protocol')
    from app.config import get_settings
    settings=get_settings();destination=OUT/'blind-verification-v1';destination.mkdir(exist_ok=True)
    manifest={'schema_version':'0.1','authoring_protocol_sha256':pointer['sha256'],'provider':'groq',
              'model':'openai/gpt-oss-120b','temperature':0.2,'reasoning_effort':'high',
              'max_tokens':4096,'timeout_seconds':180,'packet_size':1,'eligible':False}
    previous=saved_json(destination/'manifest.json',None)
    if previous is not None and previous!=manifest:raise ValueError('Verifier protocol changed')
    if previous is None:atomic_json(destination/'manifest.json',manifest)
    done=0
    with execution_lock(destination):
        for index,draft in enumerate(protocol['drafts']):
            identifier=draft['spec']['id'];source=OUT/'items'/identifier
            state=saved_json(source/'state.json',{})
            if state.get('state') not in ('drafted','protocol_held'):continue
            if state['state']=='protocol_held' and not (source/'format-repair-pointer.json').exists():continue
            from app.rag.pedagogical_repairs import load_candidate
            q,repair_sha=load_candidate(source,state)
            presentation={'questions':[{'id':identifier,'stem':q['text'],'options':q['options']}]}
            packet,mapping=make_blind_packet(presentation);prompt=solver_prompt(packet)
            binding={'candidate_sha256':payload_digest(q),'packet_sha256':payload_digest(packet),
                     'manifest_sha256':payload_digest(manifest),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
            folder=destination/identifier;folder.mkdir(exist_ok=True)
            prior=saved_json(folder/'state.json',None)
            if prior:
                if prior['binding']!=binding:raise ValueError('Stale solver binding')
                if prior['state']=='in_flight':
                    atomic_json(folder/'state.json',{**prior,'state':'interrupted_unknown','eligible':False})
                continue
            client,availability=available_client('groq',manifest['model'],0.2,settings,include_project=True,offset=index)
            if client is None:
                atomic_json(destination/'status.json',{'phase':'waiting_credentials','availability':availability});return
            transport=proxy_transport_status('groq')
            if not transport['reachable']:
                client.client.close();atomic_json(destination/'status.json',{'phase':'waiting_network','transport':transport});return
            configure_generation_client(client);client.minimum_completion_tokens=4096
            client.client.event_hooks['request'].append(request_capture(folder))
            client.client.event_hooks['response'].append(capture_hook(folder))
            atomic_json(folder/'packet.json',packet);(folder/'prompt.txt').write_bytes(prompt.encode())
            saved={'state':'in_flight','binding':binding,'started_at':now(),'eligible':False}
            atomic_json(folder/'state.json',saved)
            try:
                raw=client.generate([{'role':'user','content':prompt}],max_tokens=4096,timeout=180)
                if raw:
                    data=safe_bytes(raw.encode());sha=hashlib.sha256(data).hexdigest();(folder/(sha+'.txt')).write_bytes(data)
                    parsed=parse_solver_results(raw,packet)
                    matrix=compare_solver_results(parsed,mapping,[{'id':identifier,'answer_index':q['answer_index']}])
                    report={'matrix':matrix,'candidate_sha256':binding['candidate_sha256'],'text_only':True,
                            'figure_approval':False,'human_review':False,'eligible':False}
                    atomic_json(folder/'comparison.json',report)
                    saved.update(state='compared',response_sha256=sha,comparison_sha256=payload_digest(report))
                else:
                    saved.update(state='provider_error',error_code=trial_failure_code(getattr(client,'last_error_code',''),getattr(client,'last_error','')))
            except Exception as error:saved.update(state='held',error_code=type(error).__name__)
            finally:client.client.close()
            atomic_json(folder/'state.json',saved);done+=1
            print(json.dumps({'spec_id':identifier,'verification':saved['state']}),flush=True)
            if done>=limit:return


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--max-items',type=int,default=1);args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend' or not 1<=args.max_items<=6:raise ValueError('Run bounded trial from backend')
    solve(args.max_items)
