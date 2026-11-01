"""Assistant-reviewed checks for exact saved drafts. Never execute model code."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import sympy as S
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.pedagogical_geometry import bound_audit
from app.rag.pedagogical_authoring import parse_pedagogical_candidate
from app.rag.pedagogical_repairs import load_candidate
from scripts.prepare_pedagogical_pilot import OUT

CHECKED={'circle_power':'2d01682552239e08aaa3dff789aa18affb4e8bbac230cc255443efb79d02be6e',
         'heron_area':'d58c4fb44b6a395e0e09df79ca1a84ae018c3a6d255b49756f8593f7cbd03e8e',
         'cosine_feasibility':'e0b21d9369c81bc0c7dc811aa0413d71d1e02bd2facafbd96e99051b8d82bf31',
         'altitude_admissibility':'75198cb9da69d89592da088495d4a788e0e6a54fba5bf4152a238a7bfa9504ee'}


def circle_power(q):
    x=S.symbols('x',real=True)
    residual=S.expand((x+2)*(2*x-5)-(x-3)*(3*x-2))
    roots=S.solveset(residual,x,domain=S.S.Reals)
    feasible=S.Intersection(roots,S.Interval.open(7,S.oo))
    assert roots==S.FiniteSet(2,8) and feasible==S.FiniteSet(8)
    assert 3*8-2==22 and q['options']==['$22$','$17$','$11$','$4$'] and q['answer_index']==0
    # A concrete witness establishes that positive segment lengths coexist on
    # one circle, rather than merely satisfying an algebraic necessary condition.
    repaired=copy.deepcopy(q)
    repaired['figure']={'points':{'P':[0,0],'A':[10,0],'B':[11,0],'C':[3,4],
        'D':[13.2,17.6],'O':[10.5,9]},'segments':[['P','A'],['A','B'],['P','C'],['C','D']],
        'circles':[{'center':'O','through':'A'}]}
    relations=[{'kind':'on_circle','circle':0,'points':['A','B','C','D']},
      {'kind':'on_segment','points':['P','A','B']},{'kind':'on_segment','points':['P','C','D']},
      {'kind':'length_ratio','segments':[['P','A'],['A','B']],'value':[10,1]},
      {'kind':'length_ratio','segments':[['P','C'],['C','D']],'value':[5,17]},
      {'kind':'length_ratio','segments':[['P','D'],['P','C']],'value':[22,5]}]
    return repaired,relations,('With point order P-A-B and P-C-D, PB=2x-5 and PD=3x-2. '
       'Power gives -(x-2)(x-8)=0. Segment AB=x-7 must be positive, hence x>7 and only x=8 remains. '
       'Thus PD=22. A common-circle witness is P=(0,0), A=(10,0), B=(11,0), C=(3,4), '
       'D=(66/5,88/5), O=(21/2,9), radius squared 325/4. All four intersections lie on that circle '
       'and lengths PA,AB,PC,CD are respectively 10,1,5,17. This proves geometric existence, not just the product equation.')


def heron_area(q):
    b=S.symbols('b',real=True)
    area_squared=S.expand(10*(10-6)*(10-b)*(10-(14-b)))
    assert S.expand(area_squared-40*(9-(b-7)**2))==0
    assert S.solve_univariate_inequality((b-7)**2<9,b).as_set()==S.Interval.open(4,10)
    assert area_squared.subs(b,7)==360
    assert S.limit(area_squared,b,4,dir='+')==0 and S.limit(area_squared,b,10,dir='-')==0
    assert q['answer_index']==0 and q['options']==[
        '$(0, 6\\sqrt{10}]$','$(0, 6\\sqrt{5}]$','$(0, 12\\sqrt{5}]$','$(0, 12\\sqrt{10}]$']
    assert q['figure'] is None
    return copy.deepcopy(q),[],('Perimeter 20 and a=6 give c=14-b. The strict triangle inequalities '
      'are equivalent to 4<b<10. Heron gives S^2=40(10-b)(b-4)=360-40(b-7)^2. '
      'Therefore 0<S<=6 sqrt(10), with equality at b=c=7. For each requested area t in '
      '(0,6 sqrt(10)], take b=7+sqrt(9-t^2/40), c=7-sqrt(9-t^2/40); both lie in (4,10) '
      'and form a valid triangle with S=t. Thus every point of the claimed interval is attainable. '
      'The four option endpoints are distinct. The author alternative route merely computes the '
      'isosceles area; alone it does not prove maximality. The full Heron solution does.')


def cosine_feasibility(q):
    k=S.symbols('k',positive=True)
    product=(k**2-16)/3
    delta=S.expand(k**2-4*product)
    assert delta==(64-k**2)/3
    assert S.Intersection(S.solve_univariate_inequality(delta>=0,k).as_set(),S.Interval.open(0,S.oo))==S.Interval.Lopen(0,8)
    assert S.solve_univariate_inequality(product>0,k).as_set()==S.Interval.open(4,S.oo)
    assert S.simplify(16-delta-(k**2-16)/3)==0
    assert q['answer_index']==0 and q['options']==['$(8, 12]$','$[8, 12]$','$(8, 12)$','$(4, 12]$']
    assert q['figure'] is None
    return copy.deepcopy(q),[],('Let k=b+c>0. The cosine law at A=60 degrees and a=4 gives '
       'bc=(k^2-16)/3. Positive real b,c require k>4 and discriminant (64-k^2)/3>=0, hence 4<k<=8. '
       'Conversely, for every such k take b,c=(k plus/minus sqrt((64-k^2)/3))/2. Their product is positive '
       'and their sum positive, so both are positive. Also |b-c|<4<k, establishing all strict triangle inequalities. '
       'The cosine law then gives cos(A)=1/2. Thus every perimeter 4+k in (8,12] occurs. '
       'P=12 is the equilateral triangle of side4; P=8 is excluded degeneracy. Option1 is unique.')


def altitude_admissibility(q):
    x=S.symbols('x',positive=True)
    lo=S.Rational(1,4)-S.Rational(1,6);hi=S.Rational(1,4)+S.Rational(1,6)
    assert lo==S.Rational(1,12) and hi==S.Rational(5,12)
    feasible=[n for n in range(1,100) if lo<S.Rational(1,n)<hi]
    assert feasible==list(range(3,12)) and len(feasible)==9
    assert q['answer_index']==0 and q['options']==['$9$','$8$','$10$','$7$']
    assert q['figure'] is None
    return copy.deepcopy(q),[],('For positive area K, the sides equal 2K times the reciprocal altitudes. '
       'Consequently 1/4,1/6,1/x must satisfy strict triangle inequalities, equivalent to 1/12<1/x<5/12 '
       'or 12/5<x<12. Necessity is also sufficient: form a triangle with sides 1/4,1/6,1/x, whose area is K0>0. '
       'Its altitudes are 2K0 times 4,6,x. Scaling every length by 1/(2K0) gives exactly the required altitudes. '
       'The integer possibilities are precisely 3 through11 inclusive (nine). At either endpoint the reciprocal '
       'triangle degenerates. No integer >=12 or <=2 can work. Option1 is unique. '
       'The author solution establishes necessity but leaves this sufficiency construction implicit.')


CHECKERS={'circle_power':circle_power,'heron_area':heron_area,
          'cosine_feasibility':cosine_feasibility,'altitude_admissibility':altitude_admissibility}
REVIEW_NOTES={}


def main():
    records=[]
    for name,expected in CHECKED.items():
        folder=OUT/'items'/name
        if not (folder/'state.json').exists():continue
        state=json.loads((folder/'state.json').read_text(encoding='utf8'))
        q,repair_sha=load_candidate(folder,state)
        if payload_digest(q)!=expected:raise ValueError('Saved draft changed; requires new mathematical analysis')
        repaired,relations,proof=CHECKERS[name](q)
        def geometry(candidate):
            if candidate['figure'] is None:
                return {'candidate_sha256':payload_digest(candidate),'audit':{'all_passed':None,
                    'not_applicable':True,'reason':'No generated figure; geometry follows from the textual givens'},'eligible':False}
            return bound_audit(candidate,{'schema_version':'0.2','candidate_sha256':payload_digest(candidate),
                'figure_sha256':payload_digest(candidate['figure']),'relations':relations})
        original_audit=geometry(q);corrected_audit=geometry(repaired)
        assert repaired['figure'] is None or corrected_audit['audit']['all_passed']
        report={'spec_id':name,'candidate_sha256':expected,'format_repair_sha256':repair_sha,
            'answer_index_expected':q['answer_index'],'independent_proof':proof,
            'checked_by':'assistant_analytic_and_symbolic_check','human_scientific_review':False,
            'raw_geometry_audit':original_audit,'corrected_geometry_audit':corrected_audit,
            'corrected_candidate':repaired,'correction_scope':('Diagram only; original raw draft, text and key preserved'
                                                               if repaired!=q else 'None; original candidate retained'),
            'pedagogy_review':{'key_observation_explained':True,'domain_filter_necessary':True,
              'tag_step_references_structurally_valid':True,'technique_proposals_semantically_plausible':True,
              'human_tag_approval':False,'structural_originality':'unresolved','reviewer':'assistant',
              'remaining_limitations':(['Structured pedagogy is in English although the full solution is Persian.',
                                       'Alternative route omits the global maximum argument; use the full solution.']
                                      if name=='heron_area' else ['Full author solution leaves sufficiency implicit; independent check supplies it.']
                                      if name=='altitude_admissibility' else [])},
            'eligible':False}
        report['pedagogy_review'].update(REVIEW_NOTES.get(name,{}))
        records.append(report)
    artifact={'schema_version':'0.1','records':records,'eligible':False,'meaning':'Scoped exact-candidate checks, not expert approval'}
    folder=OUT/'independent-checks';folder.mkdir(exist_ok=True);sha=payload_digest(artifact);path=folder/(sha+'.json')
    if path.exists():
        assert json.loads(path.read_text())==artifact
    else:atomic_json(path,artifact)
    atomic_json(folder/'pointer.json',{'file':path.name,'sha256':sha})
    print(json.dumps({'mathematically_checked':len(records),'raw_diagrams_passed':sum(r['raw_geometry_audit']['audit']['all_passed'] is True for r in records),
                      'corrected_diagrams_passed':sum(r['corrected_geometry_audit']['audit']['all_passed'] is True for r in records),'artifact':str(path)}))


if __name__=='__main__':main()
