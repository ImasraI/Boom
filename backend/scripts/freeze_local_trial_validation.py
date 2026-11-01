"""Freeze verified local evidence only; never imports or writes application DB."""
import hashlib
import json
from pathlib import Path
import sys
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.blind_trial import parse_solver_results,compare_solver_results
from app.rag.local_trial_snapshot import validation_snapshot
from scripts.run_blind_authoring_trial import inputs,OUT as BLIND,REVIEW,PARENT


def bound_json(folder,name,digest):
    if Path(name).name!=name:raise ValueError('Invalid local artifact pointer')
    value=json.loads((folder/name).read_text(encoding='utf8'))
    if payload_digest(value)!=digest:raise ValueError('Artifact digest changed')
    return value


def main():
    # Reproduce the bounded checks and exact prepared payload before binding a
    # reusable snapshot. Rebased UI feedback alone cannot bless altered math.
    replay=subprocess.run([sys.executable,str(Path(__file__).with_name('check_revised_grounded_trial.py'))],
        capture_output=True,text=True,timeout=60)
    if replay.returncode:raise ValueError('Mathematical/presentation replay failed')
    presentation,packet,binding=inputs()
    state=json.loads((BLIND/'status.json').read_text())
    if state['status']!='compared' or state['binding_sha256']!=payload_digest(binding):
        raise ValueError('Blind result is missing or stale')
    report=bound_json(BLIND,state['comparison_artifact'],state['comparison_sha256'])
    raw=(BLIND/(state['response_sha256']+'.txt')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=state['response_sha256']:raise ValueError('Blind response changed')
    parsed=parse_solver_results(raw.decode('utf8'),packet)
    recomputed=compare_solver_results(parsed,binding['local_alias_mapping'],presentation['solutions'])
    if recomputed!=report['matrix']:raise ValueError('Blind comparison changed')
    ps=json.loads((REVIEW/'presentation-status.json').read_text())
    math=bound_json(PARENT,ps['check_artifact'],ps['check_sha256'])
    math=dict(math,presentation_sha256=ps['payload_sha256'])
    fs=json.loads((REVIEW/'editorial-status.json').read_text())
    feedback=bound_json(REVIEW,fs['artifact'],fs['sha256'])
    snapshot=validation_snapshot(presentation,math,report,feedback)
    snapshot['evidence_refs']=dict(math_check_sha256=ps['check_sha256'],
        blind_comparison_sha256=state['comparison_sha256'],blind_response_sha256=state['response_sha256'],
        editorial_feedback_sha256=fs['sha256'],source_packet_sha256=math['source_packet_sha256'])
    snapshot['evidence_refs']['math_replay_script_sha256']=hashlib.sha256(
        Path(__file__).with_name('check_revised_grounded_trial.py').read_bytes()).hexdigest()
    snapshot['blind_justification_audit']={
        'question_id':'grounded-revision2:2',
        'issue':'The blind solver used slope h/(a+5), omitting the vertical-side case a=−5.',
        'resolution':'Key remains4. Existing symbolic coordinate proof does not divide by this slope denominator. Exact example A(−5,5),B(10,5),C(10,0),D(0,0) gives O(4,2),P(0,2),OP=4.',
        'review_kind':'assistant_mathematical_check','human_review':False,
        'interpretation':'Answer agreement does not automatically validate every solver proof step.'}
    out=PARENT/'validation-bundle-v1';out.mkdir(exist_ok=True)
    digest=payload_digest(snapshot);name='snapshot-'+digest+'.json'
    if not (out/name).exists():atomic_json(out/name,snapshot)
    atomic_json(out/'status.json',dict(artifact=name,sha256=digest,**snapshot['summary']))
    print(json.dumps(snapshot['summary']))


if __name__=='__main__':main()
