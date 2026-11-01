"""Reproduce bounded assistant checks for explicitly bound saved drafts; no model code."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sympy as s
from app.rag.authoring_benchmark import BenchmarkStore
from app.rag.benchmark_review import checked_candidate
from app.rag.exam_corpus import atomic_json,payload_digest
from scripts.check_benchmark_algebra_slice import CASES,replay_algebra
from scripts.run_authoring_benchmark import OUT

REST={
 'pair-05-design_conditioned':('129182c219418003bb75ab6bbf8ec5f3e829bc8b1f17e435d59cb0d9dbea5956',0,
  'S=a+b obeys S^3=35+90=125, hence S=5, ab=6; actual real pair (2,3) establishes consistency. a^2+b^2=13 and fourth-power sum=13^2-2*6^2=97.'),
 'pair-06-baseline':('bb437061c5a42d8ff545389427300fce4a853bb6bbbeb5d1546b63a6c5976e4e',0,
  'u=cuberoot(9-x),v=cuberoot(7+x) have cube sum16 and sum k. k=0 is impossible. For k nonzero their product=(k^3-16)/(3k), discriminant=(64-k^3)/(3k). Exactly two distinct real pairs, hence two x values, iff 0<k<4. k=4 gives one x=1.'),
 'pair-06-design_conditioned':('fa7da749707a5287e83eeb5adce3799efce516b5192e6448d1a58a2ff576d6ea',0,
  'Use u=cuberoot(x+20),v=-cuberoot(x+4). Again cube sum16 and sum k. k=0 impossible; discriminant=(64-k^3)/(3k). Exactly two distinct x iff 0<k<4, with the bijection x=u^3-20. k=4 collapses to x=-12.'),
 'pair-07-baseline':('a0ff7d16cdd90bcfb2a1d37170999a624bae10a9125d1321dd8bd9af960f8e27',1,
  'Identity reduces the original equation to xy(x+y)=0. Over the reals its zero set is exactly the union of x=0,y=0,x+y=0. For example (1,-1) disproves the proposed two-line answer.'),
 'pair-07-design_conditioned':('530439d131b5b3111afe6c6946b3e765b0f28e7f63ab88fd5d347be880e8728a',1,
  'Factor is (x+y-1)*Q, with 2Q=(x-y)^2+(x+1)^2+(y+1)^2. Q>=0 and vanishes only at (-1,-1), a solution outside x+y=1. Division loses this point.'),
 'pair-09-baseline':('670fac7572d10fe16f6dd7317be5ad1cb8a0900120990180dc66c5017c2f5583',0,
  'Normalize B=(0,0),C=(5,0),M=(1,0),A=(u,h),h nonzero. N=((2u+3)/5,2h/5). P=lambda*A+(1-lambda)*C=t*N yields lambda=10/13, so AP/PC=3/10. Fractions and incidence are affine invariant; no symmetry is assumed.'),
 'pair-09-design_conditioned':('eabd5abb1e77ea8e8bbee10192d4c9500053823e09a3db90c9f07366bc788fae',0,
  'Normalize B=(0,0),C=(3,0),D=(1,0),A=(u,h). N=((4u+3)/7,4h/7). Writing P=lambda*A+(1-lambda)*C=t*N gives lambda=4/5; hence AP/PC=1/4 for any nondegenerate triangle.'),
 'pair-10-baseline':('9b0dbb9df311d9cfc96341a3204fe440dec8ab4e4548b6e4fc6b4c31f2c54c88',0,
  'Set B=(0,0),C=(15,0),A=(u,h),M=(m,0). K=(u/3+2m/3,h/3). The line through K parallel to AC reaches BC at N=(2m/3+5,0). BN=11 implies m=9; MC=6 and BM/MC=3/2. N lies inside MC as required.'),
 'pair-10-design_conditioned':('d62177d0adbd20aa16349377b21ca3a3c1c4fd617d5c495ac6ae8d77a4dc6f7c',1,
  'Affine normalization A=(0,3),B=(0,0),C=(3,0) gives D=(0,1),E=(2,1),P=(2/3,1). BP meets AC at F=(6/5,9/5), so AF/FC=(2/5)/(3/5)=2/3; all requested points are internal.'),
 'pair-12-baseline':('ec6059cdcddb9b5fd49a0f8132fe8139815640b3bcb6310d0256e9cb242c62ff',0,
  'Set A=(0,0),C=(12,0),B=(u,h),h nonzero. For P=t*M on DE, compare barycentric coefficients: t=x/(x+6), with 0<=x<=12. Thus 1/3<t<3/5 iff 3<x<9. This proof includes x=6, where DE is parallel to BC and the author solution extension-point argument is undefined.'),
 'pair-13-design_conditioned':('15cf37a9736c7239b0ac10529c7064949c0c25ad672884c972ef055574cec804',2,
  'Take B=(0,0),C=(3,0),D=(1,0),A=(u,h). E=A/4. K=A+3*(C-A) lies on DE because K-E=9*(D-E). Thus K is beyond C on ray AC and AK/AC=3.'),
 'pair-14-baseline':('aeeae28dfb99408fbfd2368bb29a03333a226a8f6f1dbe485588cec2162558cb',2,
  'Strict positive segments require x>2. Parallel transversals give x/(x-1)=(x+3)/4 and (x-1)/(x^2-2x)=4/6. Their root sets are {-1,3} and {1/2,3}; only3 satisfies both and positivity. AC=x+13=16. Existence: take AB=8,AC=16 and equal section fractions3/8 and5/8.'),
 'pair-14-design_conditioned':('3fcfeca498dd3af9aa59cd8953d504de16e3955e2f08a36f5c74834ba5808948',2,
  'Normalize A=(0,3),B=(0,0),C=(36,0); DE has length12 at height2. Let r=DP/DE in [0,1]. BP and CP meet AC and AB at respective heights6/(r+2),6/(3-r). Equality of these heights forces r=1/2; denominators never vanish on [0,1]. Therefore DP=6.'),
 'pair-15-baseline':('b690f5821ff21ac66fcae8b8be694f3f538d68322a6570d13d9af4aff03340b5',1,
  'Direct independent enumeration of all integers1..1200 with (n^3+n+2)%5=0, pow(3,n,7)=5 and n%4=1 yields20, exactly29+60j for j=0..19. Zero is not a solution even under a convention including it among natural numbers.'),
 'pair-15-design_conditioned':('00f11f7b0751b57e41761592ce82071c23858a529fe18a57de83c9af078ce026',1,
  'Direct independent enumeration of all two-digit integers10..99 with (n*n+pow(3,n,5))%5=0 and n%3!=0 yields13:14,26,28,32,34,46,52,68,74,86,88,92,94. Correct answer does not establish novelty; this is a scalar-range variant of the calibration construction.'),
 'pair-17-baseline':('97369da918ba032a7bdd355718c38c0f21e10c647dda19b4f89bf8d244b7d29c',1,
  'Independent modular enumeration of every integer1..500 yields214. Direct testing of seven residues gives exactly3,5,6. There are71 complete seven-blocks plus residues1,2,3 at498..500, so3*71+1=214. The endpoint500 qualifies.'),
 'pair-20-baseline':('685c1eba5b12acd74820d8deb970b0ad21f3e246c09f9c1a56586e1ca009c602',1,
  'Independent enumeration of odd integers1..203 gives exactly5,11,...,203, with34 members. The combined power residues have period6 and equal2 at residues0 and5; the oddness constraint removes residue0. The upper endpoint203 must be included.'),
 'pair-20-design_conditioned':('551754acd87c8ab9858822bbb97bc1a950f3102102f41a977121732748ea28fc',0,
  'Exhaustively test all10000 ordered pairs1..100. Exactly625 satisfy both conditions. Independently reduce exponents modulo4: the congruence allows classes(1,2),(2,3),(3,1); even x+y retains only(3,1). Each class has25 representatives, giving25*25=625.')}


def replay_rest():
    replay_algebra()
    x,y,k,u,h,m,r,t=s.symbols('x y k u h m r t',real=True)
    assert 2**3+3**3==35 and 2*3*(2+3)==30 and 2**4+3**4==97
    assert s.simplify(k*k-4*(k**3-16)/(3*k)-(64-k**3)/(3*k))==0
    assert s.expand(x**3+y**3+3*x*y-1-(x+y-1)*(x*x-x*y+y*y+x+y+1))==0
    assert s.expand(2*(x*x-x*y+y*y+x+y+1)-((x-y)**2+(x+1)**2+(y+1)**2))==0
    A=s.Matrix([u,h]);C=s.Matrix([5,0]);N=s.Matrix([(2*u+3)/5,2*h/5]);lam=s.Rational(10,13)
    assert s.simplify(lam*A+(1-lam)*C-(5*lam/2)*N)==s.zeros(2,1)
    C=s.Matrix([3,0]);N=s.Matrix([(4*u+3)/7,4*h/7]);lam=s.Rational(4,5)
    assert s.simplify(lam*A+(1-lam)*C-(7*lam/4)*N)==s.zeros(2,1)
    K=s.Matrix([u/3+2*m/3,h/3]);N=K+s.Matrix([15-u,-h])/3
    assert s.simplify(N-s.Matrix([2*m/3+5,0]))==s.zeros(2,1)
    assert s.solve(N[0]-11,m)==[9]
    F=s.Matrix([s.Rational(6,5),s.Rational(9,5)])
    assert F[0]+F[1]==3 and F[1]==3*F[0]/2
    assert s.simplify(6*(x/(x+6))-x*(1-x/(x+6)))==0
    assert s.solve(s.Eq(x/(x+6),s.Rational(1,3)),x)==[3]
    assert s.solve(s.Eq(x/(x+6),s.Rational(3,5)),x)==[9]
    assert s.diff(x/(x+6),x).subs(x,0)>0 and s.factor(s.diff(x/(x+6),x))==6/(x+6)**2
    D=s.Matrix([1,0]);E=A/4;K=A+3*(C-A)
    assert s.simplify(K-E-9*(D-E))==s.zeros(2,1)
    assert set(s.solve(x*x-2*x-3,x)) & set(s.solve(2*x*x-7*x+3,x))=={s.Integer(3)}
    assert s.solve(6/(r+2)-6/(3-r),r)==[s.Rational(1,2)]
    values=[n for n in range(1,1201) if (n**3+n+2)%5==0 and pow(3,n,7)==5 and n%4==1]
    assert values==list(range(29,1201,60)) and len(values)==20
    values=[n for n in range(10,100) if (n*n+pow(3,n,5))%5==0 and n%3!=0]
    assert values==[14,26,28,32,34,46,52,68,74,86,88,92,94]
    values=[n for n in range(1,501) if (pow(n,6,7)+3*pow(n,3,7)+2)%7==0]
    assert len(values)==214 and values[-1]==500
    assert [r for r in range(7) if (pow(r,6,7)+3*pow(r,3,7)+2)%7==0]==[3,5,6]
    values=[n for n in range(1,204) if n%2 and (pow(3,n,7)+pow(2,n,7))%7==2]
    assert values==list(range(5,204,6)) and len(values)==34
    pairs=[(x,y) for x in range(1,101) for y in range(1,101)
        if (x+y)%2==0 and (pow(2,x,5)+pow(3,y,5))%5==1]
    assert len(pairs)==625 and all(x%4==3 and y%4==1 for x,y in pairs)
    return True


def main():
    replay_rest();store=BenchmarkStore(OUT);records=[]
    for item,(sha,index,proof) in {**CASES,**REST}.items():
        q=checked_candidate(store,{'item_id':item})
        if q is None or payload_digest(q)!=sha:raise ValueError('Checked draft changed or missing')
        records.append(dict(item_id=item,candidate_sha256=sha,answer_index_expected=index,
            answer_index_actual=q['answer_index'],answer_state='matched' if q['answer_index']==index else 'disagreed',
            independent_derivation=proof,reviewer_kind='assistant',human_scientific_review=False,eligible=False))
    report=dict(schema_version='0.1',checked=len(records),records=records,
        matched=sum(r['answer_state']=='matched' for r in records),eligible=False,
        limitations=['Only these exact drafts, not missing/failed items or a global accuracy estimate',
            'Figure fidelity, proof wording, curriculum release and semantic originality remain separate',
            'Assistant symbolic/finite checks are not expert human scientific review'])
    folder=OUT/'independent-saved-slice-v1';folder.mkdir(exist_ok=True)
    name='checks-'+payload_digest(report)+'.json'
    if not (folder/name).exists():atomic_json(folder/name,report)
    atomic_json(folder/'status.json',dict(artifact=name,sha256=payload_digest(report),checked=len(records),matched=report['matched']))
    print(json.dumps(dict(checked=len(records),matched=report['matched'],eligible=0)))


if __name__=='__main__':main()
