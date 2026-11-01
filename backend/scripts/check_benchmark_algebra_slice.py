"""Replay independent, explicitly hash-bound derivations for six early drafts.

This is a narrow assistant check, not a generic verifier or human science receipt.
No generated code or mathematical expression is evaluated from model output.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sympy as s
from app.rag.authoring_benchmark import BenchmarkStore
from app.rag.benchmark_review import checked_candidate
from app.rag.exam_corpus import atomic_json,payload_digest
from scripts.run_authoring_benchmark import OUT

CASES={
 'pair-01-baseline':('fa957ade5a6af2d7a5f29a8c9f42223bfa23f50e3ca56455a6299e6f13b1065c',0,
   'Put u=cuberoot(a+x), v=cuberoot(a-x). Sum 2, product (4-a)/3; real roots iff discriminant 4(a-1)/3 >=0. Conversely each such root pair reconstructs real x=(u^3-v^3)/2 and a=(u^3+v^3)/2.'),
 'pair-02-baseline':('59a77a54af448be0d4fa4d31b85f37c0821a066c12756a72c70e285d7f6e0b85',2,
   'Equations factor as (x+y)(xy-2)=0 and (x-y)(3xy+2)=0. Branches give (0,0), two x=-y with x^2=2/3, and two x=y with x^2=2. Mixed products cannot both hold: exactly5 ordered real pairs.'),
 'pair-02-design_conditioned':('52668111aade023004019d3b13005dc61dec94d449e44bf3032e6d21e6b0b65f',3,
   'Let S=x+y,D=x-y. Second equation gives D in {-1,0,1}. First factors as (S-1)((S+2)^2+3D^2)/4=0. S=1 gives3 pairs; S=-2,D=0 adds1. Invertible real change of variables:4 total.'),
 'pair-03-baseline':('ada911bcb5830bbcaad1ab7c655fc8479d635b7abc080ce8af0a724a303d7568',0,
   'Let Q=a^2+b^2>0,S=a+b. Constraint is S(3Q-2S^2)=16, |S|<=sqrt(2Q). For z=S/sqrt(Q), maximum of z(3-2z^2) on [-sqrt2,sqrt2] is sqrt2 (check endpoints and stationary points). Hence Q>=(16/sqrt2)^(2/3)=4*cuberoot2. Equality attained at a=b=-cuberoot4.'),
 'pair-04-baseline':('af99347d63148c847058ff20e72218ee2622c6d9450ea1a24160ff18ba6bf5e7',2,
   'For k nonzero, cube-root sum k and cube sum4k imply product (k^2-4)/3; discriminant (16-k^2)/3>=0. Integers k=+-1,...,+-4 qualify. k=0 separately satisfies the equation for every real x, giving9 parameter values. Real quadratic roots reconstruct x and both radicands.'),
 'pair-05-baseline':('6603d2c14762e2c3113e4e147567aadfd12b68b04c81c8e9f98bddc617332db5',1,
   'Second equation is (x-y)^3=0, so x=y=t. First becomes 2t^3+3t^2-1=(t+1)^2(2t-1)=0. Distinct pairs are (-1,-1),(1/2,1/2):2, not3 from counting multiplicity.')}


def replay_algebra():
    x,y,S,D,t,k,a=s.symbols('x y S D t k a',real=True)
    assert s.expand((x+y)**3-x**3-y**3-6*(x+y)-3*(x+y)*(x*y-2))==0
    assert s.expand((x-y)**3-x**3+y**3-2*(x-y)+(x-y)*(3*x*y+2))==0
    first=x**3+y**3+3*x*y-1
    assert s.expand(first.subs({x:(S+D)/2,y:(S-D)/2})-(S-1)*((S+2)**2+3*D**2)/4)==0
    assert s.expand((x**3-y**3-3*x*y*(x-y))-(x-y)**3)==0
    assert s.expand((t+1)**2*(2*t-1)-(2*t**3+3*t**2-1))==0
    assert s.simplify(4-4*(4-a)/3-4*(a-1)/3)==0
    assert s.simplify(k*k-4*(k*k-4)/3-(16-k*k)/3)==0
    z=s.symbols('z',real=True);f=z*(3-2*z*z)
    points=[-s.sqrt(2),s.sqrt(2),-1/s.sqrt(2),1/s.sqrt(2)]
    assert set(s.solve(s.diff(f,z),z))==set(points[2:])
    assert all(s.simplify(s.sqrt(2)-f.subs(z,p))>=0 for p in points)
    minimum=4*s.real_root(2,3);v=-s.real_root(4,3)
    assert s.simplify(2*v*v-minimum)==0
    assert s.simplify(2*v**3-6*v**3-16)==0
    return True


def main():
    replay_algebra();store=BenchmarkStore(OUT);records=[]
    for item,(digest,index,proof) in CASES.items():
        q=checked_candidate(store,{'item_id':item})
        if q is None or payload_digest(q)!=digest:raise ValueError('Checked draft changed or missing')
        records.append(dict(item_id=item,candidate_sha256=digest,expected_answer_index=index,
            actual_answer_index=q['answer_index'],answer_state='matched' if q['answer_index']==index else 'disagreed',
            independent_derivation=proof,reviewer_kind='assistant',human_scientific_review=False,eligible=False))
    report=dict(schema_version='0.1',records=records,checked=len(records),
        disagreed=sum(r['answer_state']=='disagreed' for r in records),eligible=False,
        structural_similarity_flags=[dict(items=['pair-01-baseline','pair-04-baseline'],
            state='assistant_flag_pending_editorial_review',reason='Both reduce cube-root parameter existence to sum/product real-root feasibility; integer counting changes output but shares core construction')],
        limitations=['Six exact algebra drafts only; no other draft inherits checks',
            'Assistant derivations and symbolic identities are not human scientific approval',
            'Scope, originality and editorial judgments remain separate'])
    folder=OUT/'independent-algebra-v1';folder.mkdir(exist_ok=True)
    name='checks-'+payload_digest(report)+'.json'
    if not (folder/name).exists():atomic_json(folder/name,report)
    atomic_json(folder/'status.json',dict(artifact=name,sha256=payload_digest(report),checked=len(records),disagreed=report['disagreed']))
    print(json.dumps(dict(checked=len(records),disagreed=report['disagreed'],eligible=0)))


if __name__=='__main__':main()
