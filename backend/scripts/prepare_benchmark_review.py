"""Freeze a completed generation batch into blinded local review pages."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import BenchmarkStore,ordered_items,execution_lock,saved_json
from app.rag.benchmark_review import review_projection
from app.rag.blind_trial import make_blind_packet
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.authoring_originality import screen
from scripts.run_authoring_benchmark import ROOT,OUT,load_protocol


def development_references():
    # Development source only. Never scan folders or read reserved papers here.
    folder=ROOT/'backend/data/authoring_work/reasoning-merged-v1'
    pointer=saved_json(folder/'status.json');name=pointer['artifact']
    if Path(name).name!=name:raise ValueError('Invalid development reference pointer')
    bundle=saved_json(folder/name)
    if payload_digest(bundle)!=pointer['sha256']:raise ValueError('Development references changed')
    references=[]
    for record in bundle['records']:
        stem=record['literal']['stem']
        if isinstance(stem,list):stem=' '.join(p['value'] for p in stem)
        if not isinstance(stem,str) or not stem.strip():raise ValueError('Missing reference stem')
        references.append(dict(id=record['question_ref'],text=stem))
    if len(references)!=40:raise ValueError('Expected the bounded40-question development source')
    return references,pointer['sha256']


def calibration_references():
    folder=ROOT/'backend/data/authoring_work/grounded-authoring-trial-v1/attempt-10/review-v1'
    status=saved_json(folder/'presentation-status.json')
    presentation=saved_json(folder/'prepared-presentation.json')
    if payload_digest(presentation)!=status['payload_sha256']:raise ValueError('Calibration presentation changed')
    return [dict(id=q['id'],text=q['stem']) for q in presentation['questions']],status['payload_sha256']


def attach_local_checks(presentation,binding):
    """Attach exact draft-bound diagnostics to answer pages, never the blind packet."""
    records={r['item_id']:r for r in binding['records']}
    solutions={s['id']:s for s in presentation['solutions']}
    reports=[]
    for directory in ('independent-algebra-v1','independent-geometry-v1','quality-observations-v1'):
        folder=OUT/directory;pointer=saved_json(folder/'status.json',None)
        if pointer is None:continue
        name=pointer['artifact']
        if Path(name).name!=name:raise ValueError('Invalid check report pointer')
        report=saved_json(folder/name)
        if payload_digest(report)!=pointer['sha256']:raise ValueError('Check report changed')
        reports.append(dict(directory=directory,artifact=name,sha256=pointer['sha256']))
        for observation in report.get('records',report.get('entries',[])):
            item=observation['item_id'];record=records.get(item)
            digest=observation.get('candidate_sha256',observation.get('claims',{}).get('candidate_sha256'))
            if record is None or record['candidate_sha256']!=digest:raise ValueError('Stale independent check')
            target=solutions[record['alias']]
            if 'independent_derivation' in observation:
                target['proof']+='\n\nSeparate assistant derivation (not human scientific approval):\n'+observation['independent_derivation']
            if directory=='independent-algebra-v1':
                target['checks'].append('Independent symbolic/branch replay: '+observation['answer_state'])
            elif directory=='independent-geometry-v1':
                target['checks'].append('Coordinate claims at recorded tolerance: '+str(observation['audit']['audit']['all_passed'])+
                    '; extraction of constraints remains an assistant proposal')
            elif 'evidence' in observation:target['checks'].append('Assistant flag: '+observation['evidence'])
    binding['local_quality_reports']=reports
    binding['presentation_sha256']=payload_digest(presentation)


def main(partial=False):
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    with execution_lock(OUT):
        if partial and saved_json(OUT/'run-status.json',{}).get('phase') not in (
                'waiting_credentials','waiting_provider','waiting_network','stopped_at_boundary','stopped_at_limit'):
            raise ValueError('Partial review requires an explicitly stopped/waiting run')
        protocol,sha=load_protocol();items=ordered_items(protocol);store=BenchmarkStore(OUT)
        presentation,binding=review_projection(store,items,sha,require_complete=not partial)
        if not presentation['questions']:raise ValueError('No saved drafts to review')
        references,reference_sha=development_references()
        binding['development_surface_screen']=dict(reference_bundle_sha256=reference_sha,reference_count=len(references),
            records=[dict(alias=r['alias'],candidate_sha256=r['candidate_sha256'],
                screen=screen(r['candidate']['text'],references)) for r in binding['records']],
            semantic_originality_approved=False,reserved_sources_read=False)
        calibration,calibration_sha=calibration_references()
        binding['calibration_surface_screen']=dict(reference_presentation_sha256=calibration_sha,reference_count=len(calibration),
            records=[dict(alias=r['alias'],candidate_sha256=r['candidate_sha256'],
                screen=screen(r['candidate']['text'],calibration)) for r in binding['records']],
            semantic_originality_approved=False)
        attach_local_checks(presentation,binding)
        revision=payload_digest(binding);folder=OUT/('review-'+revision)
        folder.mkdir(exist_ok=True)
        for name,data in [('presentation.json',presentation),('binding.json',binding)]:
            path=folder/name
            if path.exists() and saved_json(path)!=data:raise ValueError('Review revision changed')
            if not path.exists():atomic_json(path,data)
        # Only answer-free stems/options leave this projection for blind solving.
        for start in range(0,len(presentation['questions']),5):
            part=dict(questions=presentation['questions'][start:start+5])
            packet,mapping=make_blind_packet(part)
            target=folder/f'blind-group-{start//5+1:02d}.json'
            data=dict(packet=packet,mapping=mapping,packet_sha256=payload_digest(packet),
                presentation_sha256=payload_digest(presentation))
            if target.exists() and saved_json(target)!=data:raise ValueError('Blind packet changed')
            if not target.exists():atomic_json(target,data)
        pages=folder/'pages';pages.mkdir(exist_ok=True)
        status_path=folder/'review-status.json'
        prior=saved_json(status_path,None)
        if prior:
            for name,digest in prior['page_sha256'].items():
                if hashlib.sha256((pages/name).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen review page changed')
        else:
            result=subprocess.run(['node',str(ROOT/'frontend/tools/render-authoring-trial.cjs'),str(pages)],
                input=json.dumps(presentation,ensure_ascii=False).encode(),capture_output=True,check=True)
            rendering=json.loads(result.stdout)
            atomic_json(status_path,dict(binding_sha256=revision,questions=len(presentation['questions']),
                rendering=rendering,page_sha256={name:hashlib.sha256((pages/name).read_bytes()).hexdigest()
                    for name in ('questions.html','solutions.html','render-validation.json')},
                blind_groups=(len(presentation['questions'])+4)//5,eligible=False))
        atomic_json(OUT/'review-pointer.json',dict(folder=folder.name,binding_sha256=revision))
        print(json.dumps(dict(folder=folder.name,questions=len(presentation['questions']),
            surface_flags=len(binding['surface_similarity_flags']),release_eligible=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partial',action='store_true',help='Saved-draft review only; not a completed comparison')
    main(parser.parse_args().partial)
