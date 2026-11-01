import json
from fractions import Fraction as F
import sympy as S
import pytest
from app.rag.calibrated_families import construct,validate_candidate,count_modular
from app.rag.model_spec_adapter import build_checked_variant


@pytest.mark.parametrize('k',[1,2,4,7,9,25,99,100])
def test_cubic_real_existence_against_direct_quadratic(k):
    q=construct('cubic_difference_feasibility',{'k':k})
    # Independent expression in x after y=x−a: 3x²−3ax+a²−k.
    x=S.symbols('x');valid=[]
    for a in range(1,25):
        roots=S.solve(3*x*x-3*a*x+a*a-k,x)
        if any(r.is_real is True for r in roots):valid.append(a)
    assert len(valid)==int(q['answer_latex'])
    assert validate_candidate(q)['valid'] and not q['eligible']


@pytest.mark.parametrize('a,b',[(15,10),(12,8),(20,7),(9,6),(49,48)])
def test_trapezoid_under_arbitrary_offsets_and_vertical_sides(a,b):
    q=construct('trapezoid_parallel_offset',{'a':a,'b':b})
    t=F(a,a+b)
    for d in (-20,0,a-b,30):
        # D=(d,1), C=(d+b,1); d=a−b gives a vertical BC.
        ox=t*(d+b);px=F(d)+(t-1)*(d+b-a)
        assert ox-px==F(b*b,a+b)
        assert t*d<px<ox<a+t*(d+b-a)
    assert q['svg'] and q['svg'].count('<text')==10
    assert len(set(q['options']))==4


def test_modular_formula_against_independent_exhaustive_counts_and_boundaries():
    count=0
    for n in range(0,5001):
        if n>0 and n%3 and (pow(3,n,5)+n*n)%5==0:count+=1
        assert count_modular(n)==count
    for n in (60,61,79,100,2026,5000):
        q=construct('modular_power_square_count',{'limit':n})
        assert int(q['answer_latex'])==count_modular(n)
        assert len(set(q['options']))==4


@pytest.mark.parametrize('family,params',[
    ('cubic_difference_feasibility',{'k':True}),('cubic_difference_feasibility',{'k':0}),
    ('cubic_difference_feasibility',{'k':7,'code':'unsafe'}),
    ('trapezoid_parallel_offset',{'a':10,'b':15}),('trapezoid_parallel_offset',{'a':10,'b':10}),
    ('trapezoid_parallel_offset',{'a':50,'b':1}),('modular_power_square_count',{'limit':59})])
def test_unsupported_domains_and_extra_parameters_held(family,params):
    with pytest.raises(ValueError):construct(family,params)


def test_safe_spec_bridge_and_tampered_proof_or_diagram_do_not_gain_approval():
    result=build_checked_variant(json.dumps({'family':'trapezoid_parallel_offset','params':{'a':15,'b':10}}))
    assert result['design_class']=='supported_practice_variant' and result['eligible'] is False
    q=result['candidate'];q['svg']=q['svg'].replace('AB=15','AB=16')
    assert validate_candidate(q)['valid'] is False
    q=construct('cubic_difference_feasibility',{'k':7});q['proof']='Unverified replacement'
    assert validate_candidate(q)['valid'] is False
