"""One answer-withheld solve per saved benchmark group; agreement is not approval."""
import hashlib
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import execution_lock,saved_json
from app.rag.blind_trial import solver_prompt,parse_solver_results,compare_solver_results
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.grounded_authoring_trial import proxy_transport_status,trial_failure_code,GENERATION_PROFILE
from scripts.run_authoring_benchmark import ROOT,OUT,available_client,capture_hook,now
from scripts.prepare_benchmark_review import main as prepare_review


def replay_prior_comparisons(review,presentation):
    """Reparse original solver responses before reusing any item result."""
    assignment=saved_json(review/'blind-verification/assignment.json')
    covered={}
    for path in sorted(review.glob('blind-group-*.json')):
        data=saved_json(path);folder=review/'blind-verification'/path.stem
        state=saved_json(folder/'status.json',None)
        if not state or state['state']!='compared':continue
        if (data['presentation_sha256']!=payload_digest(presentation)
                or data['packet_sha256']!=payload_digest(data['packet'])
                or state['binding']!={'assignment_sha256':payload_digest(assignment),'group_sha256':payload_digest(data)}):
            raise ValueError('Stale parent solver binding')
        sha=state['response_sha256']
        import re
        if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Invalid parent response reference')
        raw=(folder/(sha+'.txt')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Parent solver response changed')
        result=parse_solver_results(raw.decode(),data['packet'])
        matrix=compare_solver_results(result,data['mapping'],presentation['solutions'])
        saved=saved_json(folder/'comparison.json')
        if payload_digest(saved)!=state['comparison_sha256'] or saved['matrix']!=matrix:
            raise ValueError('Parent comparison changed')
        for entry in matrix:
            if entry['question_id'] in covered:raise ValueError('Duplicate parent item result')
            covered[entry['question_id']]=entry
    return covered


def replay_saved_verification(review,presentation):
    """Collect prior batch + single-item evidence without another provider call."""
    covered=replay_prior_comparisons(review,presentation)
    destination=review/'small-packet-verification-v1'
    manifest=saved_json(destination/'manifest.json',None)
    if manifest is None:return covered
    parent=saved_json(review/'blind-verification/assignment.json')
    binding=saved_json(review/'binding.json')
    if (manifest['parent_assignment_sha256']!=payload_digest(parent)
            or manifest['review_binding_sha256']!=payload_digest(binding)
            or manifest['parent_covered']!=sorted(covered)):
        raise ValueError('Stale recovery lineage')
    from app.rag.blind_trial import make_blind_packet
    import re
    targets=[q for q in presentation['questions'] if q['id'] not in covered]
    if manifest['targets']!=[dict(alias=q['id'],question_projection_sha256=payload_digest(q)) for q in targets]:
        raise ValueError('Recovery target changed')
    for q in targets:
        folder=destination/q['id'];state=saved_json(folder/'status.json',None)
        if not state or state['state']!='compared':continue
        packet,mapping=make_blind_packet(dict(questions=[q]))
        expected=dict(manifest_sha256=payload_digest(manifest),packet_sha256=payload_digest(packet))
        if state['binding']!=expected:raise ValueError('Stale recovery binding')
        sha=state['response_sha256']
        if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Invalid recovery response reference')
        raw=(folder/(sha+'.txt')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Recovery response changed')
        matrix=compare_solver_results(parse_solver_results(raw.decode(),packet),mapping,presentation['solutions'])
        report=saved_json(folder/'comparison.json')
        if payload_digest(report)!=state['comparison_sha256'] or report['matrix']!=matrix:
            raise ValueError('Recovery comparison changed')
        for label in ('matched','disagreed','unresolved'):
            if state[label]!=sum(r['blind_solve_state']==label for r in matrix):raise ValueError('Recovery totals changed')
        covered[q['id']]=matrix[0]
    return covered


def recover_small_packets():
    """Explicit second verification protocol; previous provider failures remain."""
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    from scripts.run_authoring_benchmark import load_protocol
    load_protocol() # Current source receipt check, no provider probe.
    pointer=saved_json(OUT/'review-pointer.json');name=pointer['folder']
    if Path(name).name!=name or not name.startswith('review-'):raise ValueError('Invalid review pointer')
    review=OUT/name;binding=saved_json(review/'binding.json');presentation=saved_json(review/'presentation.json')
    if payload_digest(binding)!=pointer['binding_sha256'] or payload_digest(presentation)!=binding['presentation_sha256']:
        raise ValueError('Review changed')
    covered=replay_prior_comparisons(review,presentation)
    targets=[q for q in presentation['questions'] if q['id'] not in covered]
    parent=saved_json(review/'blind-verification/assignment.json')
    manifest=dict(schema_version='0.1',review_binding_sha256=pointer['binding_sha256'],
        parent_assignment_sha256=payload_digest(parent),parent_covered=sorted(covered),
        provider='groq',model=parent['model'],temperature=parent['temperature'],
        profile=dict(reasoning_effort='high',completion_tokens=4096,generate_timeout_seconds=180),
        packet_size=1,targets=[dict(alias=q['id'],question_projection_sha256=payload_digest(q)) for q in targets],
        purpose='Explicit small-packet recovery after rate/request-size holds, not replacement of original outcomes',eligible=False)
    destination=review/'small-packet-verification-v1';destination.mkdir(exist_ok=True)
    from app.config import get_settings
    from app.rag.pool_usage import stage
    from app.rag.blind_trial import make_blind_packet
    settings=get_settings()
    with execution_lock(destination):
        prior=saved_json(destination/'manifest.json',None)
        if prior is not None and prior!=manifest:raise ValueError('Recovery protocol changed')
        if prior is None:atomic_json(destination/'manifest.json',manifest)
        outcomes=[]
        for q in targets:
            folder=destination/q['id'];folder.mkdir(exist_ok=True)
            state_path=folder/'status.json';saved=saved_json(state_path,None)
            packet,mapping=make_blind_packet(dict(questions=[q]))
            item_binding=dict(manifest_sha256=payload_digest(manifest),packet_sha256=payload_digest(packet))
            if saved:
                if saved['binding']!=item_binding:raise ValueError('Stale recovery item')
                if saved['state']=='in_flight':
                    saved.update(state='interrupted_unknown',eligible=False);atomic_json(state_path,saved)
                elif saved['state']=='compared':
                    import re
                    sha=saved['response_sha256']
                    if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Invalid recovery response reference')
                    raw=(folder/(sha+'.txt')).read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Recovery response changed')
                    matrix=compare_solver_results(parse_solver_results(raw.decode(),packet),mapping,presentation['solutions'])
                    report=saved_json(folder/'comparison.json')
                    if payload_digest(report)!=saved['comparison_sha256'] or report['matrix']!=matrix:
                        raise ValueError('Recovery comparison changed')
                    for field,label in [('matched','matched'),('disagreed','disagreed'),('unresolved','unresolved')]:
                        if saved[field]!=sum(r['blind_solve_state']==label for r in matrix):raise ValueError('Recovery totals changed')
                outcomes.append(saved);continue
            transport=proxy_transport_status('groq')
            if not transport['reachable']:
                atomic_json(destination/'status.json',dict(state='waiting_network',transport=transport));return
            client,availability=available_client('groq',parent['model'],parent['temperature'],settings)
            if client is None:
                atomic_json(destination/'status.json',dict(state='waiting_credentials',availability=availability));return
            client.minimum_completion_tokens=4096 # Keep high reasoning; bounded output plus ONE question.
            state=dict(state='in_flight',binding=item_binding,started_at=now(),eligible=False,human_review=False)
            atomic_json(state_path,state);prompt=solver_prompt(packet)
            (folder/'prompt.txt').write_bytes(prompt.encode())
            client.client.event_hooks['response'].append(capture_hook(folder));started=time.monotonic()
            try:
                with stage('model_evaluation'):
                    raw=client.generate([dict(role='user',content=prompt)],max_tokens=4096,timeout=180)
                if raw:
                    sha=hashlib.sha256(raw.encode()).hexdigest();(folder/(sha+'.txt')).write_bytes(raw.encode())
                    state['response_sha256']=sha
                    result=parse_solver_results(raw,packet)
                    matrix=compare_solver_results(result,mapping,presentation['solutions'])
                    report=dict(matrix=matrix,binding=item_binding,eligible=False)
                    atomic_json(folder/'comparison.json',report)
                    state.update(state='compared',comparison_sha256=payload_digest(report),
                        matched=sum(r['blind_solve_state']=='matched' for r in matrix),
                        disagreed=sum(r['blind_solve_state']=='disagreed' for r in matrix),
                        unresolved=sum(r['blind_solve_state']=='unresolved' for r in matrix))
                else:state.update(state='provider_held',error_code=trial_failure_code(client.last_error_code,client.last_error))
            except (ValueError,TypeError):state.update(state='protocol_held')
            except Exception as error:state.update(state='provider_held',error_type=type(error).__name__)
            finally:client.client.close()
            state['elapsed_seconds']=round(time.monotonic()-started,3);atomic_json(state_path,state);outcomes.append(state)
            print(json.dumps(dict(alias=q['id'],state=state['state'],matched=state.get('matched'))),flush=True)
        summary=dict(state='completed_with_holds' if any(r['state']!='compared' for r in outcomes) else 'completed',
            parent_comparisons=len(covered),recovery_targets=len(targets),
            matched=sum(r['blind_solve_state']=='matched' for r in covered.values())+sum(r.get('matched',0) for r in outcomes),
            disagreed=sum(r['blind_solve_state']=='disagreed' for r in covered.values())+sum(r.get('disagreed',0) for r in outcomes),
            unresolved=sum(r['blind_solve_state']=='unresolved' for r in covered.values())+sum(r.get('unresolved',0) for r in outcomes),
            planned_questions=len(presentation['questions']),generation_complete=binding['generation_complete'],eligible=False,human_review=False)
        summary['questions_without_comparison']=summary['planned_questions']-sum(summary[k] for k in ('matched','disagreed','unresolved'))
        atomic_json(destination/'status.json',summary);print(json.dumps(summary))


def main(partial=False):
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    prepare_review(partial=partial)
    pointer=saved_json(OUT/'review-pointer.json')
    name=pointer['folder']
    if Path(name).name!=name or not name.startswith('review-'):raise ValueError('Invalid review pointer')
    review=OUT/name;binding=saved_json(review/'binding.json')
    if payload_digest(binding)!=pointer['binding_sha256']:raise ValueError('Review binding changed')
    presentation=saved_json(review/'presentation.json')
    if payload_digest(presentation)!=binding['presentation_sha256']:raise ValueError('Presentation changed')
    destination=review/'blind-verification';destination.mkdir(exist_ok=True)
    from app.config import get_settings
    from app.rag.pool_usage import stage
    settings=get_settings()
    provider='groq';saved=saved_json(destination/'assignment.json',None)
    assignment=dict(provider=provider,model=(saved['model'] if saved else settings.POOL_LLM_MODEL_NAME or settings.LLM_MODEL_NAME),
        temperature=(saved['temperature'] if saved else settings.LLM_TEMPERATURE),profile=GENERATION_PROFILE,
        review_binding_sha256=pointer['binding_sha256'],answers_withheld=True,eligible=False)
    if saved and assignment!=saved:raise ValueError('Frozen solver assignment changed')
    if not saved:atomic_json(destination/'assignment.json',assignment)
    outcomes=[]
    with execution_lock(destination):
        for path in sorted(review.glob('blind-group-*.json')):
            data=saved_json(path)
            if data['presentation_sha256']!=payload_digest(presentation) or data['packet_sha256']!=payload_digest(data['packet']):
                raise ValueError('Blind packet changed')
            # Re-derive allowed inputs and mapping from the frozen presentation.
            from app.rag.blind_trial import make_blind_packet
            start=(int(path.stem.rsplit('-',1)[1])-1)*5
            packet,mapping=make_blind_packet(dict(questions=presentation['questions'][start:start+5]))
            if packet!=data['packet'] or mapping!=data['mapping']:raise ValueError('Invalid blind projection')
            folder=destination/path.stem;folder.mkdir(exist_ok=True)
            state_path=folder/'status.json';prior=saved_json(state_path,None)
            group_binding=dict(assignment_sha256=payload_digest(assignment),group_sha256=payload_digest(data))
            if prior:
                if prior['binding']!=group_binding:raise ValueError('Stale group outcome')
                if prior['state']=='in_flight':
                    prior.update(state='interrupted_unknown',reason='Preserved unknown consumption; no automatic replay')
                    atomic_json(state_path,prior)
                outcomes.append(prior);continue
            transport=proxy_transport_status(provider)
            if not transport['reachable']:
                atomic_json(destination/'status.json',dict(state='waiting_network',transport=transport,completed=len(outcomes)))
                return
            client,availability=available_client(provider,assignment['model'],assignment['temperature'],settings)
            if client is None:
                atomic_json(destination/'status.json',dict(state='waiting_credentials',availability=availability,completed=len(outcomes)))
                return
            state=dict(state='in_flight',binding=group_binding,started_at=now(),eligible=False,human_review=False)
            atomic_json(state_path,state)
            prompt=solver_prompt(packet);(folder/'prompt.txt').write_bytes(prompt.encode())
            client.client.event_hooks['response'].append(capture_hook(folder));started=time.monotonic()
            try:
                with stage('model_evaluation'):
                    raw=client.generate([dict(role='user',content=prompt)],
                        max_tokens=GENERATION_PROFILE['completion_tokens'],timeout=GENERATION_PROFILE['generate_timeout_seconds'])
                if raw:
                    sha=hashlib.sha256(raw.encode()).hexdigest();(folder/(sha+'.txt')).write_bytes(raw.encode())
                    state['response_sha256']=sha
                    result=parse_solver_results(raw,packet)
                    matrix=compare_solver_results(result,mapping,presentation['solutions'])
                    atomic_json(folder/'comparison.json',dict(matrix=matrix,binding=group_binding,
                        model_agreement_is_not_scientific_review=True,eligible=False))
                    state.update(state='compared',comparison_sha256=payload_digest(saved_json(folder/'comparison.json')),
                        matched=sum(r['blind_solve_state']=='matched' for r in matrix),
                        disagreed=sum(r['blind_solve_state']=='disagreed' for r in matrix),
                        unresolved=sum(r['blind_solve_state']=='unresolved' for r in matrix))
                else:state.update(state='provider_held',error_code=trial_failure_code(client.last_error_code,client.last_error))
            except (ValueError,TypeError):state.update(state='protocol_held')
            except Exception as error:state.update(state='provider_held',error_type=type(error).__name__)
            finally:client.client.close()
            state['elapsed_seconds']=round(time.monotonic()-started,3);atomic_json(state_path,state)
            outcomes.append(state)
            print(json.dumps(dict(group=path.stem,state=state['state'],matched=state.get('matched'),
                disagreed=state.get('disagreed'),unresolved=state.get('unresolved'))),flush=True)
            # Preserve this failed group, then let availability select a different
            # nonblocked credential for untouched groups. Never replay it silently.
        summary=dict(state='completed' if all(r['state']=='compared' for r in outcomes) else 'completed_with_holds',
            generation_complete=binding['generation_complete'],planned_questions=len(presentation['questions']),
            groups=len(outcomes),compared=sum(r['state']=='compared' for r in outcomes),
            matched=sum(r.get('matched',0) for r in outcomes),disagreed=sum(r.get('disagreed',0) for r in outcomes),
            unresolved=sum(r.get('unresolved',0) for r in outcomes),eligible=False,human_review=False)
        summary['questions_without_comparison']=summary['planned_questions']-sum(summary[k] for k in ('matched','disagreed','unresolved'))
        atomic_json(destination/'status.json',summary);print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partial',action='store_true',help='Verify only the explicit saved-draft snapshot; not a completed benchmark')
    parser.add_argument('--recover-small',action='store_true',help='Explicit answer-withheld recovery for previously unverified items')
    args=parser.parse_args()
    if args.recover_small:recover_small_packets()
    else:main(args.partial)
