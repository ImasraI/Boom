"""Checked practice variants of the three calibrated trial designs.

Pure bounded declarative construction, no providers or corpus access. Neither a
variant nor its inferred design inherits the user's review of the original item.
"""
from fractions import Fraction as F
from math import isqrt
import random
import json

FAMILIES=('cubic_difference_feasibility','trapezoid_parallel_offset','modular_power_square_count')
VERSION='calibrated-practice-0.1'


def integer(params,key,low,high):
    value=params.get(key)
    if type(value) is not int or not low<=value<=high:raise ValueError('Unsupported integer parameter')
    return value


def latex(value):
    value=F(value)
    return str(value.numerator) if value.denominator==1 else r'\frac{'+str(value.numerator)+'}{'+str(value.denominator)+'}'


def count_modular(limit):
    if type(limit) is not int or not 0<=limit<=1000000:raise ValueError('Unsupported limit')
    blocks,tail=divmod(limit,60)
    return 8*blocks+sum(r<=tail for r in (8,14,26,28,32,34,46,52))


def trapezoid_svg(a,b):
    # Deliberately asymmetric valid coordinates; every intersection is derived
    # from the same parameters as the answer. Fixed viewbox, no arbitrary SVG.
    d=F(a-b,3);t=F(a,a+b);scale=F(330,a)
    def pt(x,y):return float(40+scale*x),float(50+280*y)
    A=pt(0,0);B=pt(a,0);D=pt(d,1);C=pt(d+b,1)
    M=pt(t*d,t);N=pt(a+t*(d+b-a),t);O=pt(t*(d+b),t);P=pt(d+(t-1)*(d+b-a),t)
    points={'A':A,'B':B,'C':C,'D':D,'M':M,'N':N,'O':O,'P':P}
    def line(x,y,color='#777'):
        p,q=points[x],points[y]
        return f'<line x1="{p[0]:.3f}" y1="{p[1]:.3f}" x2="{q[0]:.3f}" y2="{q[1]:.3f}" stroke="{color}" stroke-width="1.5"/>'
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 430 400" role="img" aria-label="Trapezoid with parallel segment and diagonal intersection">'
    svg+='<polygon points="'+' '.join(f'{points[k][0]:.3f},{points[k][1]:.3f}' for k in 'ABCD')+'" fill="none" stroke="#333" stroke-width="2"/>'
    svg+=''.join(line(x,y) for x,y in [('A','C'),('B','D'),('D','P')])+line('M','N','#91483e')
    shifts={'A':(-15,-12),'B':(8,-12),'C':(8,20),'D':(-15,20),'M':(-20,4),'N':(8,4),'O':(-5,-13),'P':(-5,24)}
    for k,(x,y) in points.items():
        dx,dy=shifts[k];svg+=f'<text x="{x+dx:.3f}" y="{y+dy:.3f}" font-size="16">{k}</text>'
    svg+=f'<text x="180" y="32" font-size="15">AB={a}</text><text x="180" y="374" font-size="15">CD={b}</text></svg>'
    return svg


def construct(family,params):
    if not isinstance(params,dict):raise ValueError('Typed parameters required')
    svg=None
    if family=='cubic_difference_feasibility':
        if set(params)!={'k'}:raise ValueError('Only k is allowed')
        k=integer(params,'k',1,100)
        answer=isqrt(4*k)
        values=[F(answer),F(answer-1),F(answer+1),F(2*answer)]
        stem=(rf'پارامتر $a$ صحیح مثبت و $x,y$ حقیقی‌اند. دستگاه $$\begin{{cases}}x^3-y^3={k}a\\x-y=a\end{{cases}}$$ '
              'برای چند مقدارِ $a$ حداقل یک پاسخ حقیقی دارد؟')
        proof=f'Substitute x=y+a and divide by a>0: 3y²+3ay+a²−{k}=0. Discriminant=12·{k}−3a². Real existence iff a²≤{4*k}; there are floor(sqrt({4*k}))={answer} positive integer parameters. Equality is admitted.'
        checks=['Positive integer a and real x,y are explicit. Quadratic discriminant gives necessity and sufficiency.']
    elif family=='trapezoid_parallel_offset':
        if set(params)!={'a','b'}:raise ValueError('Only a,b are allowed')
        a=integer(params,'a',2,50);b=integer(params,'b',1,49)
        if not b<a<=3*b:raise ValueError('Require longer top base and bounded diagram aspect ratio')
        answer=F(b*b,a+b)
        values=[answer,F(a*b,a+b),F(b),F(b,2)]
        stem=(rf'در ذوزنقهٔ $ABCD$، قاعده‌ها $AB={a}$ و $CD={b}$ موازی‌اند. قطرها در $O$ همدیگر را قطع می‌کنند. '
              r'خط گذرنده از $O$ و موازی قاعده‌ها، ساق‌های $AD$ و $BC$ را در $M$ و $N$ قطع می‌کند. '
              r'خط گذرنده از $D$ و موازی $BC$، پاره‌خط $MN$ را در $P$ قطع می‌کند. طول $OP$ کدام است؟')
        proof=f'Let A=(0,0),B=({a},0),D=(d,h),C=(d+{b},h),h>0. Diagonals give t=AO/AC={a}/{a+b}. Then MO=ON=ab/(a+b), PN=b from parallelogram DCNP, and MP=b(a−b)/(a+b)>0. Therefore OP=b²/(a+b)={answer}. This avoids division by any side slope.'
        svg=trapezoid_svg(a,b)
        checks=['All points/intersections and SVG derive from a,b. a>b ensures M<P<O<N. No reflection symmetry assumed.']
    elif family=='modular_power_square_count':
        if set(params)!={'limit'}:raise ValueError('Only limit is allowed')
        n=integer(params,'limit',60,5000)
        answer=count_modular(n)
        unfiltered=4*(n//20)+sum(r<=n%20 for r in (6,8,12,14))
        naive=2*(n//20)+max(0,sum(r<=n%20 for r in (6,8,12,14))-2)
        values=[F(answer),F(unfiltered),F(naive),F(answer+1)]
        stem=(rf'چند عدد صحیح $n$ در بازهٔ $1\le n\le {n}$ وجود دارد که بر $3$ بخش‌پذیر نباشد و $3^n+n^2$ بر $5$ بخش‌پذیر باشد؟')
        proof=f'Powers3 modulo5 have period4; squares modulo5 have period5. First condition has residues6,8,12,14 modulo20. Combine the nonmultiple-of3 restriction: valid residues in1..60 are8,14,26,28,32,34,46,52. Count complete60-blocks and the final partial block: {answer}. Do not subtract a constant number per20-block.'
        checks=['Exact periodic enumeration, with a separate partial-block count and explicit positive integer interval.']
    else:raise ValueError('Unsupported family')
    if len(set(values))!=4:raise ValueError('Equivalent answer options')
    random.Random(family+json.dumps(params,sort_keys=True)).shuffle(values)
    answer=F(answer)
    return dict(family=family,parameters=dict(params),constructor_version=VERSION,stem=stem,
        options=['$'+latex(v)+'$' for v in values],answer_index=values.index(answer),
        answer_latex=latex(answer),svg=svg,figure=None,proof=proof,checks=checks,
        difficulty=None,eligible=False,human_reviewed=False)


def validate_candidate(candidate):
    expected=construct(candidate['family'],candidate['parameters'])
    fields=('constructor_version','stem','options','answer_index','answer_latex','svg','figure','proof','checks','difficulty','eligible','human_reviewed')
    return dict(valid=all(candidate.get(k)==expected[k] for k in fields),eligible=False,
        limitations=['Supported practice family, not a new reasoning design',
            'No inherited human review of parameter variants','Curriculum/novelty/release gates remain separate'])
