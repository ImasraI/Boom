"""Two additional unpublished constructions; no corpus/provider access."""
from fractions import Fraction
import random
import sympy as S

FAMILIES = ('quadratic_open_interval_count', 'conditional_dice_divisibility')


def construct(family, params):
    if params:
        raise ValueError('This revision has no configurable parameters')
    if family == 'quadratic_open_interval_count':
        answer = S.Union(S.Interval.open(-S.oo,0), S.FiniteSet(1), S.Interval(S.Rational(4,3),S.oo))
        stem = r'به ازای کدام مقادیر حقیقی $t$، معادلهٔ $x^2-2tx+t=0$ دقیقاً یک ریشهٔ متمایز در بازهٔ باز $(0,2)$ دارد؟ ریشهٔ مضاعف، یک ریشهٔ متمایز شمرده می‌شود.'
        values = [answer, S.Union(S.Interval.open(-S.oo,0),S.Interval.open(S.Rational(4,3),S.oo)),
                  S.Union(S.Interval.open(-S.oo,0),S.Interval(S.Rational(4,3),S.oo)),
                  S.Union(S.Interval(-S.oo,0),S.FiniteSet(1),S.Interval(S.Rational(4,3),S.oo))]
        proof = ('Discriminant/4=t(t-1). For t<0, endpoint signs f(0)<0<f(2) give one root inside. '
                 'At t=0 the only root is the excluded endpoint. For 0<t<1 no real roots exist. '
                 'At t=1 there is one distinct double root x=1. For 1<t<4/3 both roots are inside: '
                 'the vertex lies in (1,4/3), f(0)>0, f(2)>0 and its value t-t² is negative. '
                 'At t=4/3 the roots are 2/3 and the excluded endpoint 2. For t>4/3 opposite endpoint signs give one inside.')
        checks = ['Exact discriminant and endpoint cases including isolated t=1 and excluded roots at x=0,2.']
    elif family == 'conditional_dice_divisibility':
        outcomes=[(a,b) for a in range(1,7) for b in range(1,7)]
        condition=[(a,b) for a,b in outcomes if a!=b and (a*b)%6==0]
        favorable=[(a,b) for a,b in condition if a+b in (2,3,5,7,11)]
        ratio=Fraction(len(favorable),len(condition));answer=S.Rational(ratio.numerator,ratio.denominator)
        stem = r'دو تاس سالم و متمایز را یک‌بار می‌اندازیم. می‌دانیم دو عدد ظاهرشده متفاوت‌اند و حاصل‌ضرب آن‌ها بر $6$ بخش‌پذیر است. با این اطلاعات، احتمال اینکه مجموع دو عدد، عددی اول باشد، کدام است؟'
        values=[answer,S.Rational(1,2),S.Rational(1,3),S.Rational(2,3)]
        if len(set(values))!=4:raise ValueError('Distractor collision')
        proof=f'The 36 ordered equiprobable outcomes are conditioned on distinct faces and product divisible by 6. There are {len(condition)} conditioned outcomes, of which {len(favorable)} have prime sum. Ordered favorable pairs: {favorable}. Probability={answer}.'
        checks=['All 36 ordered outcomes enumerated with exact rational weights; conditioning denominator is nonzero.']
    else:
        raise ValueError('Unsupported new family')
    random.Random(835).shuffle(values)
    return dict(family=family,parameters={},stem=stem,options=['$'+S.latex(x)+'$' for x in values],
                answer_index=values.index(answer),answer_latex=S.latex(answer),proof=proof,checks=checks,
                figure=None,svg=None,difficulty=None,eligible=False)


def validate_candidate(candidate):
    expected=construct(candidate['family'],candidate['parameters'])
    fields=('stem','options','answer_index','answer_latex','figure','difficulty','eligible')
    return {'valid':all(candidate.get(k)==expected[k] for k in fields),'eligible':False,
            'limitations':['human_quality_pending','curriculum_mapping_pending','not_independent_blind_model_solve']}
