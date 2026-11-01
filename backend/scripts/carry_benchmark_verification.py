"""Revalidate old blind responses and carry exact candidates forward, offline."""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import execution_lock,saved_json
from app.rag.benchmark_review import carry_verified_results
from app.rag.exam_corpus import atomic_json,payload_digest
from scripts.run_authoring_benchmark import ROOT,OUT,load_protocol
from scripts.solve_benchmark_blind import replay_saved_verification


def load_review(name):
    if not re.fullmatch(r'review-[0-9a-f]{64}',name):raise ValueError('Expected a private review revision name')
    folder=OUT/name;binding=saved_json(folder/'binding.json');presentation=saved_json(folder/'presentation.json')
    if payload_digest(binding)!=name.removeprefix('review-') or payload_digest(presentation)!=binding['presentation_sha256']:
        raise ValueError('Review evidence changed')
    return folder,binding,presentation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-review',required=True)
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    with execution_lock(OUT):
        load_protocol()
        pointer=saved_json(OUT/'review-pointer.json')
        current,binding,presentation=load_review(pointer['folder'])
        previous,old_binding,old_presentation=load_review(args.prior_review)
        verified=replay_saved_verification(previous,old_presentation)
        matrix=carry_verified_results(old_binding,binding,old_presentation,presentation,verified)
        report=dict(schema_version='0.1',source_review=args.prior_review,target_review=current.name,
            matrix=matrix,matched=sum(r['blind_solve_state']=='matched' for r in matrix),
            disagreed=sum(r['blind_solve_state']=='disagreed' for r in matrix),
            unresolved=sum(r['blind_solve_state']=='unresolved' for r in matrix),
            questions_without_comparison=len(presentation['questions'])-len(matrix),
            provider_calls=0,eligible=False,human_scientific_review=False,
            scope='Exact raw candidate/text-only evidence; no figure or human approval inherited')
        name='carried-verification-'+payload_digest(report)+'.json'
        if not (current/name).exists():atomic_json(current/name,report)
        atomic_json(current/'carried-verification-pointer.json',dict(artifact=name,sha256=payload_digest(report)))
        print(json.dumps({k:report[k] for k in ('matched','disagreed','unresolved','questions_without_comparison','provider_calls')}))


if __name__=='__main__':main()
