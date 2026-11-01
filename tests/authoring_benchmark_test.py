import hashlib
import json
import pytest
from app.rag.authoring_benchmark import (BenchmarkStore, BenchmarkBusy, execution_lock,
    authoring_prompt, parse_candidate, figure_svg, ordered_items)
from app.rag.exam_corpus import atomic_json
from app.rag.exam_corpus import payload_digest
from app.rag.benchmark_review import review_projection, normalized


def candidate():
    return dict(text='Synthetic $x=2$?', options=['1','2','3','4'],answer_index=1,
        solution='x = 2',design={k:'Synthetic evidence' for k in
        ('givens','unknown','domains','essential_insight','structural_departure','tempting_wrong_route')},figure=None)


def test_only_conditioned_arm_contains_guidance():
    task=dict(brief_id='cubic_identity',target='Count real feasible pairs')
    a=authoring_prompt(task,'baseline');b=authoring_prompt(task,'design_conditioned')
    common_a=json.loads(a.split('Data:\n')[1]);common_b=json.loads(b.split('Data:\n')[1])
    assert common_b.pop('design_guidance')
    assert common_a==common_b
    assert a.split('Data:\n')[0]==b.split('Data:\n')[0]
    assert 'source_packet_sha256' not in b


@pytest.mark.parametrize('mutation',[
    lambda q:q.update(answer_index=True),
    lambda q:q.update(options=['1','1','2','3']),
    lambda q:q.update(eligible=True),
    lambda q:q.update(text='bad\ftext'),
    lambda q:q.update(figure={'points':{'<script>':[0,0],'B':[1,1]},'segments':[]}),
    lambda q:q.update(figure={'points':{'A':[float('nan'),0],'B':[1,1]},'segments':[]}),
    lambda q:q.update(figure={'points':{'A':[0,0],'B':[1,1]},'segments':[['A','C']]}),
])
def test_malformed_output_is_held(mutation):
    q=candidate();mutation(q)
    with pytest.raises(ValueError):parse_candidate(json.dumps(q))


def test_valid_output_and_declarative_svg():
    q=candidate();q['figure']={'points':{'A':[0,0],'B':[3,4]},'segments':[['A','B']]}
    assert parse_candidate(json.dumps(q))==q
    svg=figure_svg(q['figure'])
    assert '<line' in svg and 'x2="292.500"' in svg and 'y2="45.000"' in svg
    assert 'direction="ltr"' in svg
    assert '<script' not in svg


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError):parse_candidate('{"text":"x","text":"y"}')


def test_exclusive_execution_and_release(tmp_path):
    with execution_lock(tmp_path):
        with pytest.raises(BenchmarkBusy):
            with execution_lock(tmp_path):pass
    with execution_lock(tmp_path):pass


def test_assignment_outcomes_and_paths_are_immutable(tmp_path):
    store=BenchmarkStore(tmp_path);store.freeze_assignment({'model':'synthetic'})
    with pytest.raises(ValueError):store.freeze_assignment({'model':'changed'})
    with pytest.raises(ValueError):store.folder('../escape')
    assert store.begin('pair-01-baseline',{'prompt':'a'})
    store.finish('pair-01-baseline',dict(state='drafted',eligible=False))
    assert not store.begin('pair-01-baseline',{'prompt':'a'})
    with pytest.raises(ValueError):store.begin('pair-01-baseline',{'prompt':'b'})
    with pytest.raises(ValueError):store.finish('pair-01-baseline',dict(state='drafted',eligible=False))


def test_corrupt_checkpoint_never_restarts(tmp_path):
    store=BenchmarkStore(tmp_path)
    (store.folder('pair-01-baseline')/'state.json').write_text('{broken')
    with pytest.raises(ValueError):store.begin('pair-01-baseline',{})


def test_saved_response_recovers_without_new_request(tmp_path):
    store=BenchmarkStore(tmp_path);item='pair-01-baseline';store.begin(item,{'prompt':'a'})
    folder=store.folder(item);raw=json.dumps(candidate()).encode();sha=hashlib.sha256(raw).hexdigest()
    (folder/f'fragment-{sha}.txt').write_bytes(raw)
    atomic_json(folder/'transport-events.json',[dict(http_status=200,finish_reason='stop',
        fragments=[dict(kind='visible_content',sha256=sha)])])
    store.recover(item)
    assert store.state(item)['state']=='drafted'
    assert not store.begin(item,{'prompt':'a'})
    assert json.loads((folder/'candidate.json').read_text())==candidate()


def test_unknown_interruption_is_not_retried(tmp_path):
    store=BenchmarkStore(tmp_path);item='pair-01-baseline';store.begin(item,{})
    store.recover(item)
    assert store.state(item)['state']=='interrupted_unknown'
    assert not store.begin(item,{})


def test_summary_distinguishes_failures_and_arms(tmp_path):
    protocol={'tasks':[dict(spec_id=f'dev-pair:{i:02}',brief_id='cubic_identity',
        arm_order='baseline_first',target='synthetic') for i in range(1,21)]}
    items=ordered_items(protocol);store=BenchmarkStore(tmp_path)
    for item,state in zip(items,['provider_refused','protocol_held']):
        store.begin(item['item_id'],{});store.finish(item['item_id'],dict(state=state,eligible=False))
    s=store.summary(items)
    assert s['planned']==40 and s['pending']==38 and s['release_eligible']==0
    assert s['arms']['baseline']['provider_refused']==1
    assert s['arms']['design_conditioned']['protocol_held']==1


def complete_synthetic_batch(tmp_path):
    protocol={'tasks':[dict(spec_id=f'dev-pair:{i:02}',brief_id='cubic_identity',
        arm_order='baseline_first',target='synthetic') for i in range(1,21)]}
    items=ordered_items(protocol);store=BenchmarkStore(tmp_path)
    assignment={'protocol_sha256':'synthetic'};store.freeze_assignment(assignment)
    for item in items:
        folder=store.folder(item['item_id'])
        store.begin(item['item_id'],{'assignment_sha256':payload_digest(assignment)})
        q=candidate();raw=json.dumps(q).encode();sha=hashlib.sha256(raw).hexdigest()
        (folder/(sha+'.txt')).write_bytes(raw);atomic_json(folder/'candidate.json',q)
        store.finish(item['item_id'],dict(state='drafted',eligible=False,response_sha256=sha))
    return store,items


def test_review_aliases_are_stable_and_answer_free(tmp_path):
    store,items=complete_synthetic_batch(tmp_path)
    page,binding=review_projection(store,items,'synthetic')
    assert len(page['questions'])==40 and binding['eligible'] is False
    assert all(set(q)=={'id','stem','options','svg'} for q in page['questions'])
    assert all('baseline' not in q['id'] for q in page['questions'])
    assert len(binding['surface_similarity_flags'])==780
    assert review_projection(store,items,'synthetic')==(page,binding)
    assert normalized('۴ x + 2',True)==normalized('9 x + 3',True)


def test_edited_candidate_cannot_reuse_generation_binding(tmp_path):
    store,items=complete_synthetic_batch(tmp_path)
    path=store.folder(items[0]['item_id'])/'candidate.json'
    q=candidate();q['answer_index']=3;atomic_json(path,q)
    with pytest.raises(ValueError,match='Candidate changed'):review_projection(store,items,'synthetic')


def test_prior_blind_solve_carry_requires_identical_literal_key_and_no_approval(tmp_path):
    from app.rag.benchmark_review import carry_verified_results
    import copy
    store,items=complete_synthetic_batch(tmp_path)
    presentation,binding=review_projection(store,items,'synthetic');alias=presentation['questions'][0]['id']
    row=dict(question_id=alias,blind_solve_state='matched',solver_verdict='solved',solver_answer_index=1,
        expected_answer_index=1,justification='Synthetic independent proof',human_scientific_review=False,eligible=False)
    result=carry_verified_results(binding,binding,presentation,presentation,{alias:row})
    assert result[0]['text_only'] and result[0]['figure_approval'] is False and result[0]['eligible'] is False
    changed=copy.deepcopy(presentation);changed['questions'][0]['stem']='Changed wording'
    new_binding={**binding,'presentation_sha256':payload_digest(changed)}
    with pytest.raises(ValueError):carry_verified_results(binding,new_binding,presentation,changed,{alias:row})
    for mutation in [dict(human_scientific_review=True),dict(eligible=True),dict(blind_solve_state='disagreed'),
            dict(solver_answer_index=True),dict(scientific_approved=True)]:
        with pytest.raises(ValueError):carry_verified_results(binding,binding,presentation,presentation,{alias:{**row,**mutation}})


def test_changed_raw_output_cannot_be_reviewed(tmp_path):
    store,items=complete_synthetic_batch(tmp_path);item=items[0]['item_id']
    path=store.folder(item)/(store.state(item)['response_sha256']+'.txt')
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='Response changed'):review_projection(store,items,'synthetic')


def test_incomplete_batch_cannot_be_exported_as_complete(tmp_path):
    store=BenchmarkStore(tmp_path);store.freeze_assignment({'protocol_sha256':'synthetic'})
    with pytest.raises(ValueError,match='not complete'):
        review_projection(store,[{'item_id':'pair-01-baseline'}],'synthetic')


def test_explicit_partial_snapshot_retains_pending_and_stable_aliases(tmp_path):
    store,items=complete_synthetic_batch(tmp_path)
    full,binding=review_projection(store,items,'synthetic')
    # Synthetic test fixture removal only; production checkpoints are never reset.
    folder=store.folder(items[0]['item_id']);(folder/'state.json').unlink()
    partial,p=review_projection(store,items,'synthetic',require_complete=False)
    assert len(partial['questions'])==39 and p['planned_items']==40 and not p['generation_complete']
    assert len([r for r in p['states'] if r['state']=='unattempted'])==1
    assert {r['item_id']:r['alias'] for r in p['states']}=={r['item_id']:r['alias'] for r in binding['states']}
    store.begin(items[0]['item_id'],{'assignment_sha256':payload_digest({'protocol_sha256':'synthetic'})})
    with pytest.raises(ValueError):review_projection(store,items,'synthetic',require_complete=False)


def runner_fixture(monkeypatch,tmp_path,reachable=True):
    from scripts import run_authoring_benchmark as runner
    from types import SimpleNamespace
    protocol={'tasks':[dict(spec_id=f'dev-pair:{i:02}',brief_id='cubic_identity',
        arm_order='baseline_first',target='synthetic') for i in range(1,21)],
        'generation_profile':{'completion_tokens':16384,'generate_timeout_seconds':180}}
    monkeypatch.setattr(runner,'OUT',tmp_path)
    monkeypatch.setattr(runner,'load_protocol',lambda:(protocol,'synthetic'))
    monkeypatch.setattr(runner,'proxy_transport_status',lambda p:{'reachable':reachable})
    atomic_json(tmp_path/'status.json',{'artifact':'synthetic','sha256':'synthetic'})
    from app import config
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(GEMINI_MODEL_NAME='synthetic-model',LLM_TEMPERATURE=.2))
    class Client:
        calls=0
        last_error_code=''
        last_error=''
        def __init__(self):self.client=SimpleNamespace(close=lambda:None,event_hooks={'response':[]})
        def generate(self,*args,**kwargs):
            Client.calls+=1
            return json.dumps(candidate())
    monkeypatch.setattr(runner,'available_client',lambda *args:(Client(),{}))
    return runner,Client


def test_runner_resume_skips_finished_items(monkeypatch,tmp_path):
    runner,client=runner_fixture(monkeypatch,tmp_path)
    runner.run('gemini',1);first=(tmp_path/'items/pair-01-baseline/state.json').read_bytes()
    runner.run('gemini',1)
    assert client.calls==2
    assert (tmp_path/'items/pair-01-baseline/state.json').read_bytes()==first
    assert json.loads((tmp_path/'run-status.json').read_text())['completed']==2
    with pytest.raises(ValueError,match='assignment'):runner.run('groq',1)
    assert client.calls==2


def test_runner_does_not_consume_attempt_on_network_preflight_failure(monkeypatch,tmp_path):
    runner,client=runner_fixture(monkeypatch,tmp_path,False)
    runner.run('gemini',1)
    assert client.calls==0
    assert not (tmp_path/'items/pair-01-baseline/state.json').exists()
    assert json.loads((tmp_path/'run-status.json').read_text())['phase']=='waiting_network'


def test_runner_honors_provider_cooldown(monkeypatch,tmp_path):
    import time
    runner,client=runner_fixture(monkeypatch,tmp_path)
    atomic_json(tmp_path/'run-status.json',{'phase':'waiting_provider','retry_not_before':time.time()+300})
    runner.run('gemini',1)
    assert client.calls==0


def test_project_key_scope_uses_active_envs_only_and_deduplicates(monkeypatch,tmp_path):
    from scripts import run_authoring_benchmark as runner
    from types import SimpleNamespace
    (tmp_path/'backend').mkdir()
    (tmp_path/'backend/.env').write_text('GEMINI_API_KEY=AQ.synthetic_primary\nGEMINI_PROXY=direct\n')
    for name,key in [('worker1','AQ.synthetic_primary'),('worker2','AQ.synthetic_extra')]:
        folder=tmp_path/'ocr-workers'/name;folder.mkdir(parents=True)
        (folder/'worker.env').write_text(f'GEMINI_API_KEY={key}\nGEMINI_PROXY=direct\n')
    backup=tmp_path/'backend/data/credential_backups';backup.mkdir(parents=True)
    (backup/'old.env').write_text('GEMINI_API_KEY=AQ.retired_not_authorized\n')
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    settings=SimpleNamespace(POOL_LLM_PROVIDER='groq',LLM_PROVIDER='groq',POOL_GEMINI_API_KEYS='AQ.synthetic_primary')
    assert runner.candidate_keys('gemini',settings)==['AQ.synthetic_primary']
    assert runner.candidate_keys('gemini',settings,True)==['AQ.synthetic_primary','AQ.synthetic_extra']


def test_expanded_scope_respects_saved_scanner_refusals(monkeypatch,tmp_path):
    from scripts import run_authoring_benchmark as runner
    from app.rag import llm,provider_quota
    from types import SimpleNamespace
    import time
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(runner,'candidate_keys',lambda *args:['bad','daily','ready'])
    monkeypatch.setattr(provider_quota,'blocked_access',lambda i:None)
    monkeypatch.setattr(provider_quota,'blocked_quota',lambda i:None)
    monkeypatch.setattr(provider_quota,'rate_limited',lambda i:0)
    closed=[]
    class Fake:
        def __init__(self,api_key,base_url,model,**kwargs):
            self._quota_identity=provider_quota.quota_identity(base_url,model,api_key)
            self.client=SimpleNamespace(close=lambda:closed.append(api_key))
    monkeypatch.setattr(llm,'GeminiLLMClient',Fake)
    base='https://example.invalid/openai';model='fixed-model'
    path=tmp_path/'backend/data/exam_examples/vision-quota.json';path.parent.mkdir(parents=True)
    atomic_json(path,{provider_quota.quota_identity(base,model,'bad'):{'access_denied':True},
        provider_quota.quota_identity(base,model,'daily'):{'error':'provider_daily_quota','retry_at':time.time()+600}})
    before=path.read_bytes()
    selected,metadata=runner.available_client('gemini',model,.2,SimpleNamespace(GEMINI_BASE_URL=base),True)
    assert selected._quota_identity==provider_quota.quota_identity(base,model,'ready')
    assert closed==['bad','daily'] and metadata=={'available':True}
    assert path.read_bytes()==before


def test_review_render_keeps_aliases_and_withholds_answers():
    from pathlib import Path
    import subprocess
    import tempfile
    import shutil
    root=Path(__file__).resolve().parents[1]
    parent=root/'backend/data/authoring_work'
    parent.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='synthetic-benchmark-render-',dir=parent))
    try:
        page=dict(review_only=True,proof_kind='independent_assistant',questions=[dict(id='R17',stem='Synthetic $\\invalidCommand$',
            options=['one','two','three','four'],svg=None)],solutions=[dict(id='R17',answer_index=2,
            answer_latex='',proof='SECRET_ANSWER_BEARING_PROOF',checks=['Pending verification'])])
        result=subprocess.run(['node',str(root/'frontend/tools/render-authoring-trial.cjs'),str(folder)],
            input=json.dumps(page).encode(),capture_output=True,check=True)
        assert json.loads(result.stdout)['errors']==1
        question=(folder/'questions.html').read_text(encoding='utf8')
        assert 'R17' in question and 'SECRET_ANSWER_BEARING_PROOF' not in question
        answers=(folder/'solutions.html').read_text(encoding='utf8')
        assert 'SECRET_ANSWER_BEARING_PROOF' in answers
        assert 'دستیار' in answers and 'مدل نویسنده' not in answers
    finally:
        assert folder.resolve().parent==parent.resolve()
        shutil.rmtree(folder)


def test_blind_benchmark_solver_withholds_author_answers_and_does_not_replay(monkeypatch,tmp_path):
    from scripts import solve_benchmark_blind as solver
    from app.rag.blind_trial import make_blind_packet
    from types import SimpleNamespace
    store,items=complete_synthetic_batch(tmp_path)
    presentation,binding=review_projection(store,items,'synthetic')
    revision=payload_digest(binding);review=tmp_path/('review-'+revision);review.mkdir()
    atomic_json(review/'binding.json',binding);atomic_json(review/'presentation.json',presentation)
    atomic_json(tmp_path/'review-pointer.json',{'folder':review.name,'binding_sha256':revision})
    for start in range(0,40,5):
        packet,mapping=make_blind_packet({'questions':presentation['questions'][start:start+5]})
        atomic_json(review/f'blind-group-{start//5+1:02d}.json',dict(packet=packet,mapping=mapping,
            packet_sha256=payload_digest(packet),presentation_sha256=payload_digest(presentation)))
    monkeypatch.setattr(solver,'OUT',tmp_path)
    monkeypatch.setattr(solver,'prepare_review',lambda **kwargs:None)
    monkeypatch.setattr(solver,'ROOT',__import__('pathlib').Path.cwd().parent)
    monkeypatch.setattr(solver,'proxy_transport_status',lambda p:{'reachable':True})
    from app import config
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(POOL_LLM_MODEL_NAME='synthetic-solver',LLM_TEMPERATURE=.2))
    class Client:
        calls=0
        def __init__(self):self.client=SimpleNamespace(close=lambda:None,event_hooks={'response':[]})
        def generate(self,messages,**kwargs):
            Client.calls+=1;prompt=messages[0]['content']
            packet=json.loads(prompt.split('Data:\n')[1])
            assert all(set(q)=={'id','text','options'} for q in packet['questions'])
            assert 'Synthetic evidence' not in prompt and 'x = 2' not in prompt
            return json.dumps({'results':[dict(id=q['id'],verdict='solved',answer_index=1,
                justification='Synthetic independent derivation') for q in packet['questions']]})
    monkeypatch.setattr(solver,'available_client',lambda *args:(Client(),{}))
    solver.main();solver.main()
    assert Client.calls==8
    outcome=json.loads((review/'blind-verification/status.json').read_text())
    assert outcome['matched']==40 and outcome['eligible'] is False and outcome['human_review'] is False
    covered=solver.replay_prior_comparisons(review,presentation)
    assert len(covered)==40
    first=next(iter(covered))
    monkeypatch.setattr(solver,'replay_prior_comparisons',lambda *args:{k:v for k,v in covered.items() if k!=first})
    from scripts import run_authoring_benchmark
    monkeypatch.setattr(run_authoring_benchmark,'load_protocol',lambda:({},'synthetic'))
    solver.recover_small_packets();solver.recover_small_packets()
    assert Client.calls==9
    recovery=review/'small-packet-verification-v1'
    outcome=json.loads((recovery/'status.json').read_text())
    assert outcome['matched']==40 and outcome['recovery_targets']==1 and outcome['human_review'] is False
    manifest=json.loads((recovery/'manifest.json').read_text())
    assert manifest['profile']['reasoning_effort']=='high' and manifest['profile']['completion_tokens']==4096
    state=json.loads((recovery/first/'status.json').read_text());state['matched']=2
    atomic_json(recovery/first/'status.json',state)
    with pytest.raises(ValueError,match='totals changed'):solver.recover_small_packets()


def test_six_exact_algebra_derivations_replay():
    from scripts.check_benchmark_algebra_slice import replay_algebra
    assert replay_algebra() is True


def test_saved_slice_symbolic_and_finite_derivations_replay():
    from scripts.check_benchmark_saved_slice import replay_rest
    assert replay_rest() is True


def test_presentation_correction_is_bound_and_preserves_raw(monkeypatch):
    from scripts import build_benchmark_checked_preview as builder
    import copy
    q=candidate();q['options'][3]='$([0, 4)$';frozen=copy.deepcopy(q)
    monkeypatch.setattr(builder,'REST',{'pair-06-baseline':(payload_digest(q),0,'synthetic')})
    revised,changes=builder.corrected_candidate('pair-06-baseline',q)
    assert q==frozen and revised!=q and changes
    q['text']='Changed after binding'
    with pytest.raises(ValueError,match='input changed'):builder.corrected_candidate('pair-06-baseline',q)


def test_check_attachments_are_bound_and_never_enter_blind_questions(monkeypatch,tmp_path):
    from scripts import prepare_benchmark_review as builder
    from app.rag.blind_trial import make_blind_packet
    store,items=complete_synthetic_batch(tmp_path)
    page,binding=review_projection(store,items,'synthetic')
    r=binding['records'][0]
    report=dict(records=[dict(item_id=r['item_id'],candidate_sha256=r['candidate_sha256'],
        independent_derivation='ANSWER_BEARING_INDEPENDENT_PROOF',answer_state='matched')])
    folder=tmp_path/'independent-algebra-v1';folder.mkdir()
    atomic_json(folder/'checks.json',report)
    atomic_json(folder/'status.json',dict(artifact='checks.json',sha256=payload_digest(report)))
    monkeypatch.setattr(builder,'OUT',tmp_path)
    builder.attach_local_checks(page,binding)
    assert binding['presentation_sha256']==payload_digest(page)
    assert 'ANSWER_BEARING_INDEPENDENT_PROOF' in json.dumps(page['solutions'])
    packet,_=make_blind_packet({'questions':page['questions'][:5]})
    assert 'ANSWER_BEARING_INDEPENDENT_PROOF' not in json.dumps(packet)
    report['records'][0]['candidate_sha256']='changed'
    atomic_json(folder/'checks.json',report)
    atomic_json(folder/'status.json',dict(artifact='checks.json',sha256=payload_digest(report)))
    with pytest.raises(ValueError,match='Stale'):builder.attach_local_checks(page,binding)
