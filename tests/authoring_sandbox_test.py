"""Independent finite/symbolic checks and adversarial candidate mutations."""
from copy import deepcopy
from fractions import Fraction
import itertools
import pytest
import sympy as S
from app.rag.authoring_sandbox import FAMILIES,construct,solve,validate_candidate


@pytest.mark.parametrize("family",FAMILIES)
def test_supported_instances_have_unique_answers_and_no_difficulty_or_promotion(family):
    item=construct(family,seed=19)
    assert validate_candidate(item)["valid"]
    assert len(set(item["options"]))==4
    assert item["difficulty"] is item["empirical_difficulty"] is None
    assert item["eligible"] is False


@pytest.mark.parametrize("mutation",["key","duplicate","equivalent_option","stem","answer","figure","difficulty","promotion"])
def test_bad_or_unreviewed_changes_are_rejected(mutation):
    item=construct("ordered_cubic_roots")
    if mutation=="key":item["answer_index"]=(item["answer_index"]+1)%4
    if mutation=="duplicate":item["options"][0]=item["options"][1]
    if mutation=="equivalent_option":item["options"][(item["answer_index"]+1)%4]="$12/2$"
    if mutation=="stem":item["stem"]+=" Unchecked extra constraint."
    if mutation=="answer":item["answer_latex"]="8"
    if mutation=="figure":item["figure"]={"P":["0","0"]}
    if mutation=="difficulty":item["difficulty"]="hard"
    if mutation=="promotion":item["eligible"]=True
    assert validate_candidate(item)["valid"] is False


def test_original_domain_holes_cannot_be_filled_by_cancellation():
    result=solve("trig_domain_level_set",{})["answer"]
    assert S.sqrt(2) not in result and 0 not in result and 2 not in result
    assert 1 in result and S.Rational(3,2) in result


def test_ordered_cubic_rejects_the_repeated_root_candidate():
    x=S.symbols("x")
    assert S.factor(x**3-6*x**2+9*x+4-8)==(x-4)*(x-1)**2
    roots=S.solve(x**3-6*x**2+9*x-2,x)
    assert set(roots)=={S.Integer(2),2-S.sqrt(3),2+S.sqrt(3)}
    assert S.simplify((2-S.sqrt(3))*(2+S.sqrt(3)))==1


@pytest.mark.parametrize("width,height",[(3,10),(7,4),(6,6)])
def test_area_family_keeps_givens_and_answer_under_affine_scaling(width,height):
    result=solve("cevian_area_ratio",dict(width=width,height=height))
    pts={k:tuple(S.Rational(v) for v in xy) for k,xy in result["figure"].items()}
    assert pts["D"]==(S.Rational(width,2),0)
    assert pts["P"]==(S.Rational(2*width,5),S.Rational(height,5))
    assert pts["E"]==(S.Rational(2*width,3),S.Rational(height,3))
    assert result["answer"]==S.Rational(1,15)


def test_grid_count_is_not_the_independent_row_product():
    # Different implementation: enumerate pairs of permutations instead of3^6 colourings.
    rows=list(itertools.permutations("RGB"))
    count=sum(sum(x==y for x,y in zip(a,b))==1 for a in rows for b in rows)
    assert count==18 and count!=len(rows)**2


def test_conditional_probability_from_hypergeometric_events():
    # Unordered first-two event: equal likelihood in both urns leaves the prior unchanged.
    eventA=Fraction(3*1,6);eventB=Fraction(1*3,6)
    priorA=Fraction(1,3);priorB=Fraction(2,3)
    posteriorA=priorA*eventA/(priorA*eventA+priorB*eventB)
    assert posteriorA==Fraction(1,3)
    assert solve("conditional_third_draw",{})["answer"]==S.Rational(posteriorA.numerator,posteriorA.denominator)


def test_digit_constraints_bind_reversal_and_both_nonzero_digits():
    values=[10*a+b for a in range(1,10) for b in range(1,10) if a-b==3 and (10*a+b)%7 in (3,4)]
    assert values==[52,74]
    assert solve("digit_reversal_congruence",{})["answer"]==len(values)


@pytest.mark.parametrize("params",[{"a":True},{"a":0},{"a":9,"b":2},{"code":"__import__('os')"}])
def test_parameters_are_bounded_values_not_executable_code(params):
    with pytest.raises(ValueError):construct("absolute_line_intersections",params)


def test_parameterized_intersection_family_preserves_boundary_conditions():
    for params in [dict(a=1,b=3),dict(a=4,b=9)]:
        assert solve("absolute_line_intersections",params)["answer"]==S.Interval.open(-2,2)
    with pytest.raises(ValueError):solve("unknown",{})
