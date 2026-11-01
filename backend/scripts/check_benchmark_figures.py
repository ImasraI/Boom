"""Coordinate audit for the eight saved geometry schematics, separate from keys."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import BenchmarkStore
from app.rag.benchmark_review import checked_candidate
from app.rag.figure_constraints import audit_bound_relations
from app.rag.exam_corpus import atomic_json,payload_digest
from scripts.check_benchmark_saved_slice import REST
from scripts.run_authoring_benchmark import OUT


def on(a,p,b):return dict(kind='on_segment',points=[a,p,b])
def line(a,p,b):return dict(kind='collinear',points=[a,p,b])
def ratio(a,b,c,d,n,m):return dict(kind='length_ratio',segments=[[a,b],[c,d]],value=[n,m])
def parallel(a,b,c,d):return dict(kind='parallel',segments=[[a,b],[c,d]])

RELATIONS={
 'pair-09-baseline':[on('A','D','B'),on('A','E','C'),parallel('D','E','B','C'),ratio('A','D','D','B',3,2),
    on('B','M','C'),ratio('B','M','M','C',1,4),on('A','N','M'),on('D','N','E'),line('B','N','P'),
    on('A','P','C'),ratio('A','P','P','C',3,10)],
 'pair-09-design_conditioned':[on('B','D','C'),ratio('B','D','D','C',1,2),on('A','N','D'),
    ratio('A','N','N','D',3,4),line('B','N','P'),on('A','P','C'),ratio('A','P','P','C',1,4)],
 'pair-10-baseline':[on('A','D','B'),ratio('A','D','D','B',2,1),on('A','E','C'),parallel('D','E','B','C'),
    on('B','M','C'),on('A','K','M'),on('D','K','E'),on('B','N','C'),parallel('K','N','A','C'),
    ratio('B','N','N','C',11,4),ratio('B','M','M','C',3,2)],
 'pair-10-design_conditioned':[on('A','D','B'),ratio('A','D','D','B',2,1),on('A','E','C'),parallel('D','E','B','C'),
    on('D','P','E'),ratio('D','P','P','E',1,2),line('B','P','F'),on('A','F','C'),ratio('A','F','F','C',2,3)],
 'pair-12-baseline':[on('A','D','B'),ratio('A','D','D','B',1,1),on('B','M','C'),ratio('B','M','M','C',1,1),
    on('A','N','M'),ratio('A','N','A','M',1,3),on('A','K','M'),ratio('A','K','A','M',3,5),
    on('A','E','C'),on('A','P','M'),on('D','P','E'),on('N','P','K')],
 'pair-13-design_conditioned':[on('B','D','C'),ratio('B','D','D','C',1,2),on('A','E','B'),
    ratio('A','E','E','B',3,1),line('D','E','K'),line('A','C','K'),ratio('A','K','A','C',3,1)],
 'pair-14-baseline':[on('A','D','B'),on('D','F','B'),on('A','E','C'),on('E','G','C'),
    parallel('D','E','B','C'),parallel('F','G','B','C'),ratio('A','D','A','B',3,8),
    ratio('A','F','A','B',5,8),ratio('A','E','A','C',3,8),ratio('A','G','A','C',5,8),ratio('A','D','A','E',1,2)],
 'pair-14-design_conditioned':[on('A','D','B'),ratio('A','D','D','B',1,2),on('A','E','C'),
    parallel('D','E','B','C'),on('D','P','E'),line('B','P','M'),line('C','P','N'),on('A','M','C'),
    on('A','N','B'),parallel('M','N','B','C'),ratio('D','P','P','E',1,1)]}


def audit_candidate(item,candidate):
    claims=dict(schema_version='0.1',candidate_sha256=payload_digest(candidate),
        figure_sha256=payload_digest(candidate['figure']),relations=RELATIONS[item])
    return audit_bound_relations(candidate,claims)


def main():
    store=BenchmarkStore(OUT);records=[]
    for item in RELATIONS:
        q=checked_candidate(store,{'item_id':item})
        if q is None or payload_digest(q)!=REST[item][0]:raise ValueError('Audited candidate changed')
        records.append(dict(item_id=item,candidate_sha256=payload_digest(q),audit=audit_candidate(item,q)))
    report=dict(schema_version='0.1',records=records,checked=len(records),
        coordinate_claim_passes=sum(r['audit']['audit']['all_passed'] for r in records),eligible=False,
        limitations=['Assistant-extracted constraints; extraction is not human-reviewed',
            'Strict1e-7 tolerance flags rounding separately from a wrong answer',
            'Coordinate consistency is not scientific or originality approval'])
    folder=OUT/'figure-audits-v1';folder.mkdir(exist_ok=True);name='audits-'+payload_digest(report)+'.json'
    if not (folder/name).exists():atomic_json(folder/name,report)
    atomic_json(folder/'status.json',dict(artifact=name,sha256=payload_digest(report),checked=len(records),
        coordinate_claim_passes=report['coordinate_claim_passes']))
    print(json.dumps(dict(checked=len(records),coordinate_claim_passes=report['coordinate_claim_passes'],eligible=0)))


if __name__=='__main__':main()
