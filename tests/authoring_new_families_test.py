from fractions import Fraction
import sympy as S
from app.rag.authoring_new_families import construct,validate_candidate,FAMILIES
from app.rag.model_spec_adapter import build_checked_variant
import json


def test_quadratic_against_exact_root_enumeration():
    x=S.symbols('x')
    for t in set([S.Rational(n,12) for n in range(-36,61)]+[S.Rational(4,3),S.Integer(1)]):
        roots=S.solve(x*x-2*t*x+t,x)
        count=sum(bool(r.is_real and r>0 and r<2) for r in set(roots))
        assert (count==1)==bool(t<0 or t==1 or t>=S.Rational(4,3))


def test_dice_by_unordered_pairs_with_two_equal_weights():
    pairs=[(a,b) for a in range(1,7) for b in range(a+1,7) if a*b%6==0]
    good=[(a,b) for a,b in pairs if S.isprime(a+b)]
    expected=Fraction(len(good),len(pairs))
    item=construct('conditional_dice_divisibility',{})
    assert item['answer_latex']==S.latex(S.Rational(expected.numerator,expected.denominator))


def test_new_adapter_checks_final_wording_and_key():
    for family in FAMILIES:
        result=build_checked_variant(json.dumps({'family':family,'params':{}}))
        assert result['validation']['valid']
        item=result['candidate'];item['answer_index']=(item['answer_index']+1)%4
        assert not validate_candidate(item)['valid']
